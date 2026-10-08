"""Voz de referencia local Qwen3-TTS Base, opcional y serializada."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import subprocess
import numpy as np
import soundfile as sf
from app.tts.audio import _ffmpeg_bin

class PersonalVoice:
    sample_rate = 24000

    def __init__(self, settings):
        for name in ("personal_voice_model", "personal_voice_reference", "personal_voice_transcript"):
            value = getattr(settings, name)
            if value is None or not Path(value).exists():
                raise ValueError(f"Falta configurar {name}")
        # Un único hilo posee el modelo y las operaciones Metal.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="personal-voice")
        self.reference = str(settings.personal_voice_reference)
        self.transcript = settings.personal_voice_transcript.read_text().strip()
        if not self.transcript:
            raise ValueError("La transcripción de referencia está vacía")
        try:
            self._executor.submit(self._load, str(settings.personal_voice_model)).result()
        except Exception:
            self._executor.shutdown(wait=False)
            raise

    def _load(self, path):
        from mlx_audio.tts.utils import load_model
        self.model = load_model(path)
        if getattr(self.model.config, "tts_model_type", "") != "base":
            raise ValueError("La voz personal requiere un modelo Qwen3-TTS Base")
        self.sample_rate = self.model.sample_rate

    def generate(self, text, speed):
        if not 0.1 < speed <= 3.0:
            raise ValueError("Velocidad inválida")
        return self._executor.submit(self._generate, text, speed).result()

    def _generate(self, text, speed):
        parts = [np.asarray(x.audio, dtype=np.float32) for x in self.model.generate(
            text=text, ref_audio=self.reference, ref_text=self.transcript,
            lang_code="spanish", temperature=.6, max_tokens=2048)]
        audio = np.concatenate(parts)
        if not np.isfinite(audio).all():
            raise ValueError("Audio inválido")
        return change_tempo(audio, self.sample_rate, speed)

    def close(self):
        self._executor.shutdown(wait=True)

def change_tempo(audio, sample_rate, speed):
    """Ajusta la duración sin transponer la voz; no depende del speed ignorado por Qwen."""
    if speed == 1:
        return audio
    factors = []
    remaining = speed
    while remaining < .5:
        factors.append(.5)
        remaining /= .5
    while remaining > 2:
        factors.append(2.)
        remaining /= 2
    factors.append(remaining)
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp)/"in.wav", Path(tmp)/"out.wav"
        sf.write(src, audio, sample_rate, subtype="FLOAT")
        subprocess.run([_ffmpeg_bin(), "-v", "error", "-y", "-i", str(src),
                        "-af", ",".join(f"atempo={f}" for f in factors), str(dst)],
                       check=True, capture_output=True)
        out, sr = sf.read(dst, dtype="float32")
        if sr != sample_rate:
            raise ValueError("Frecuencia inesperada")
        return out
