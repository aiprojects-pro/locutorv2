"""CPU-only Qwen voice adapter; Linux performance must be measured on target."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import numpy as np
from app.tts.personal import change_tempo

class PersonalCPUVoice:
    sample_rate = 24000

    def __init__(self, settings):
        for key in ('personal_voice_model', 'personal_voice_reference', 'personal_voice_transcript'):
            value = getattr(settings, key)
            if value is None or not Path(value).exists():
                raise ValueError(f'Falta configurar {key}')
        config = json.loads((settings.personal_voice_model/'config.json').read_text())
        if config.get('tts_model_type') != 'base' or config.get('quantization') or config.get('quantization_config'):
            raise ValueError('Se requiere Qwen Base original para PyTorch, no el modelo MLX cuantizado.')
        self.reference = str(settings.personal_voice_reference)
        self.transcript = settings.personal_voice_transcript.read_text().strip()
        if not self.transcript:
            raise ValueError('La transcripción de referencia está vacía')
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='personal-cpu')
        try:
            self._executor.submit(self._load, str(settings.personal_voice_model), settings.num_threads).result()
        except Exception:
            self._executor.shutdown(wait=True)
            raise

    def _load(self, path, threads):
        import torch
        from qwen_tts import Qwen3TTSModel
        torch.set_num_threads(max(1, threads))
        # FP32 and eager attention avoid assuming GPU/BF16 support on the target.
        self.model = Qwen3TTSModel.from_pretrained(
            path, device_map='cpu', dtype=torch.float32,
            attn_implementation='eager', local_files_only=True)
        with torch.inference_mode():
            self.prompt = self.model.create_voice_clone_prompt(
                ref_audio=self.reference, ref_text=self.transcript, x_vector_only_mode=False)

    def generate(self, text, speed):
        if not 0.1 < speed <= 3.0:
            raise ValueError('Velocidad inválida')
        return self._executor.submit(self._generate, text, speed).result()

    def _generate(self, text, speed):
        import torch
        with torch.inference_mode():
            wavs, sr = self.model.generate_voice_clone(
                text=text, language='Spanish', voice_clone_prompt=self.prompt,
                temperature=.6, max_new_tokens=2048)
        if len(wavs) != 1 or sr != self.sample_rate:
            raise ValueError('Salida de voz inesperada')
        audio = np.asarray(wavs[0], dtype=np.float32)
        if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
            raise ValueError('Audio inválido')
        return change_tempo(audio, sr, speed)

    def close(self):
        self._executor.shutdown(wait=True)
