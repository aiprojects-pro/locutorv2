"""Create isolated trial settings; never overwrite secrets or existing config."""
from pathlib import Path
import os,secrets

def main():
    root=Path.cwd()
    if (root/'.env').exists():
        raise SystemExit('.env ya existe; no se sobrescribe')
    for name in ('data','data/jobs','data/benchmark','models','private'):
        (root/name).mkdir(parents=True,exist_ok=True)
    for name in ('referencia_13s.wav','referencia_13s.txt'):
        if not (root/'private'/name).is_file():raise SystemExit('Falta referencia privada')
    (root/'config/personal-only.yaml').write_text('default: personal\nvoices: []\n')
    values={
        'SECRET_KEY':secrets.token_urlsafe(48),'API_BEARER_TOKEN':'',
        'COOKIE_SECURE':'true','TRUST_PROXY':'false',
        'PERSONAL_VOICE_ENABLED':'true','PERSONAL_VOICE_BACKEND':'torch_cpu',
        'PERSONAL_VOICE_DEFAULT':'true',
        'PERSONAL_VOICE_MODEL':str(root/'models/qwen-base'),
        'PERSONAL_VOICE_REFERENCE':str(root/'private/referencia_13s.wav'),
        'PERSONAL_VOICE_TRANSCRIPT':str(root/'private/referencia_13s.txt'),
        'VOICES_CONFIG':str(root/'config/personal-only.yaml'),
        'NUM_THREADS':'4','CONCURRENCY':'1','MAX_CONCURRENT_JOBS':'1',
        'CHUNK_MAX_CHARS':'400','MAX_INPUT_CHARS':'3000','PER_CHUNK_TIMEOUT_S':'1800',
        'DEFAULT_SPEED':'0.9','DEFAULT_MUSIC':'calma','SILENCE_MS':'350','MP3_BITRATE':'192k',
        'DB_URL':f'sqlite:///{root}/data/locutor.db','WORK_DIR':str(root/'data/jobs'),
        'HF_HOME':str(root/'data/hf-cache'),'HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
        'OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4',
    }
    fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(''.join(f'{k}={v}\n' for k,v in values.items()))
    print('Configuración privada creada; cookies HTTPS activadas.')
if __name__=='__main__':main()
