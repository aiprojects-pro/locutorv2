"""Fetch public model weights at a fixed revision; never reads voice files."""
from pathlib import Path
import json,os
REPO='Qwen/Qwen3-TTS-12Hz-1.7B-Base'
REVISION='fd4b254389122332181a7c3db7f27e918eec64e3'
if __name__=='__main__':
    os.environ['HF_HUB_OFFLINE']='0'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    from huggingface_hub import snapshot_download
    path=Path(os.environ.get('PERSONAL_VOICE_MODEL', 'models/qwen-base')).resolve()
    snapshot_download(REPO,revision=REVISION,local_dir=path)
    (path/'locutor-model-revision.json').write_text(json.dumps({'repo':REPO,'revision':REVISION},indent=2))
    print('Modelo descargado en',path)
