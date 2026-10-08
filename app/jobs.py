"""Gestor de trabajos TTS en memoria (proceso único).

Flujo de cada trabajo:
  texto -> normalización -> fragmentos -> generación (pool) -> MP3.

La generación bloqueante se ejecuta SIEMPRE fuera del event loop, en un
ThreadPoolExecutor acotado a `concurrency` (coincide con el pool del motor, de
modo que num_threads * concurrency no sobre-suscribe la CPU).

Nota: un timeout por fragmento NO cancela la generación nativa en curso; solo
marca el trabajo como fallido. El trabajo real se acota con chunk_max_chars y
max_input_chars.
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.logging_conf import get_logger
from app.tts.audio import assemble_mp3
from app.tts.chunk import chunk_text
from app.tts.engine import VoiceRegistry
from app.tts.normalize import TextNormalizer

logger = get_logger("locutor.jobs")

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"


@dataclass
class Job:
    id: str
    user_id: int
    source_name: str
    voice_key: str = ""
    status: str = STATUS_PENDING
    total_chunks: int = 0
    done_chunks: int = 0
    error: str | None = None
    mp3_path: Path | None = None
    music_mp3_path: Path | None = None
    music: str = "none"
    created_at: float = field(default_factory=time.time)

    stage: str = "queued"
    started_at: float | None = None
    finished_at: float | None = None
    chunk_started_at: float | None = None

    @property
    def progress(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return round(self.done_chunks / self.total_chunks, 3)

    def public(self) -> dict:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "elapsed_seconds": max(0, int((self.finished_at or time.monotonic()) - self.started_at)) if self.started_at is not None else 0,
            "chunk_elapsed_seconds": max(0, int(time.monotonic() - self.chunk_started_at)) if self.chunk_started_at is not None and self.status == STATUS_PROCESSING else 0,
            "total_chunks": self.total_chunks,
            "done_chunks": self.done_chunks,
            "error": self.error,
            "music_download_url": f"/jobs/{self.id}/download?variant=music" if self.status == STATUS_DONE and self.music_mp3_path else None,
            "music": self.music,
            "download_url": f"/jobs/{self.id}/download" if self.status == STATUS_DONE else None,
        }


class JobManager:
    def __init__(self, settings: Settings, engine: VoiceRegistry, normalizer: TextNormalizer):
        self.settings = settings
        self.engine = engine
        self.normalizer = normalizer
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._chunk_pool = ThreadPoolExecutor(
            max_workers=max(1, settings.concurrency), thread_name_prefix="tts-chunk"
        )
        self._job_pool = ThreadPoolExecutor(
            max_workers=max(1, settings.max_concurrent_jobs), thread_name_prefix="tts-job"
        )

    # --- API ------------------------------------------------------------

    def create(self, user_id: int, text: str, source_name: str, voice_key: str, speed: float, music: str = "none") -> Job:
        from app.tts.music import MUSIC
        if music not in {"none", *MUSIC}:
            raise ValueError("Música inválida")
        self._cleanup_expired()
        job = Job(id=uuid.uuid4().hex, user_id=user_id, source_name=source_name, voice_key=voice_key, music=music)
        with self._lock:
            self._jobs[job.id] = job
        self._job_pool.submit(self._run, job, text, voice_key, speed)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_for_user(self, user_id: int) -> list[Job]:
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.user_id == user_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    # --- procesamiento --------------------------------------------------

    def _run(self, job: Job, text: str, voice_key: str, speed: float) -> None:
        start = time.time()
        try:
            job.started_at = time.monotonic()
            job.stage = "preparing"
            job.status = STATUS_PROCESSING
            normalized = self.normalizer.normalize(text)
            chunks = chunk_text(normalized, self.settings.chunk_max_chars)
            if not chunks:
                raise ValueError("El documento no contiene texto locutable.")
            job.total_chunks = len(chunks)

            # Enviar un fragmento cada vez evita llenar la cola y seguir generando
            # un documento entero cuando falla una parte o vence su tiempo.
            results = []
            for index, chunk in enumerate(chunks, 1):
                job.stage = "synthesizing"
                job.chunk_started_at = time.monotonic()
                fut = self._chunk_pool.submit(self.engine.generate, voice_key, chunk, speed)
                try:
                    results.append(fut.result(timeout=self.settings.per_chunk_timeout_s))
                except FutureTimeout:
                    # Cancel queued work; an already-running native call cannot be stopped.
                    fut.cancel()
                    raise
                logger.info("fragmento completado", extra={
                    "event": "chunk_done", "job_id": job.id,
                    "chunk_index": index, "total_chunks": len(chunks),
                    "duration_ms": int((time.monotonic() - job.chunk_started_at) * 1000),
                })
                job.done_chunks += 1

            job.chunk_started_at = None
            job.stage = "exporting"
            out_dir = self.settings.work_dir / job.id
            mp3_path = out_dir / "audio.mp3"
            music_path = out_dir / "audio_music.mp3" if job.music != "none" else None
            assemble_mp3(
                results,
                self.engine.sample_rate_for(voice_key),
                mp3_path,
                silence_ms=self.settings.silence_ms,
                bitrate=self.settings.mp3_bitrate,
                music=job.music, music_mp3=music_path,
            )
            job.mp3_path = mp3_path
            job.music_mp3_path = music_path
            job.stage = "done"
            job.status = STATUS_DONE
            logger.info(
                "trabajo completado",
                extra={"job_id": job.id, "event": "job_done", "status": "done",
                       "duration_ms": int((time.time() - start) * 1000)},
            )
        except FutureTimeout:
            job.stage = "error"
            job.status = STATUS_ERROR
            job.error = "Tiempo de generación excedido en un fragmento."
            logger.warning("timeout de fragmento", extra={"job_id": job.id, "event": "job_timeout"})
        except Exception as exc:  # noqa: BLE001 - se registra y se expone genérico
            job.stage = "error"
            job.status = STATUS_ERROR
            job.error = "Error al generar el audio."
            logger.exception("error en trabajo", extra={"job_id": job.id, "event": "job_error"})

        finally:
            job.finished_at = time.monotonic()
            job.chunk_started_at = None

    # --- limpieza -------------------------------------------------------

    def _cleanup_expired(self) -> None:
        ttl = self.settings.job_ttl_seconds
        now = time.time()
        expired: list[Job] = []
        with self._lock:
            for jid, job in list(self._jobs.items()):
                if job.status in {STATUS_DONE, STATUS_ERROR} and now - job.created_at > ttl:
                    expired.append(job)
                    del self._jobs[jid]
        for job in expired:
            job_dir = self.settings.work_dir / job.id
            try:
                if job_dir.exists():
                    for f in job_dir.iterdir():
                        f.unlink(missing_ok=True)
                    job_dir.rmdir()
            except OSError:
                pass

    def shutdown(self) -> None:
        self._job_pool.shutdown(wait=True, cancel_futures=True)
        self._chunk_pool.shutdown(wait=True, cancel_futures=True)
