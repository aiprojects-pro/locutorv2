"""Real CPU benchmark, same normalizer/chunks/audio export as the app."""
from pathlib import Path
import os,time,json,resource,platform
from dotenv import load_dotenv
load_dotenv()
os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
from app.config import get_settings
from app.tts.engine import VoiceRegistry,load_voices
from app.tts.normalize import load_normalizer
from app.tts.chunk import chunk_text
from app.tts.audio import assemble_mp3

def main():
    settings=get_settings()
    if settings.personal_voice_backend!='torch_cpu':raise SystemExit('Se requiere torch_cpu')
    out=settings.work_dir.parent/'benchmark';out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();engine=VoiceRegistry(settings,*load_voices(settings))
    engine.load();load_s=time.monotonic()-start
    try:
        text=Path('samples/prueba.txt').read_text()
        chunks=chunk_text(load_normalizer(settings.normalization_config).normalize(text),settings.chunk_max_chars)
        start=time.monotonic()
        audio=[engine.generate('personal',c,.9) for c in chunks]
        generation=time.monotonic()-start
        sr=engine.sample_rate_for('personal')
        duration=sum(len(x) for x in audio)/sr
        assemble_mp3(audio,sr,out/'solo_voz.mp3',settings.silence_ms,'192k','calma',out/'con_calma.mp3')
        report={'platform':platform.platform(),'threads':settings.num_threads,
                'load_seconds':load_s,'generation_seconds':generation,'audio_seconds':duration,
                'seconds_per_audio_second':generation/duration,
                'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if platform.system()=='Linux' else 1024**2),
                'quality':'Pendiente de escucha y comparación con samples/referencia_resultado_mac.mp3'}
        (out/'informe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:engine.close()
if __name__=='__main__':main()
