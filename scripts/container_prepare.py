"""Validate runtime inputs and initialize a persistent public model download."""
from pathlib import Path
import json,os,subprocess,sys
from scripts.download_cpu_model import REVISION

def validate():
    key=os.environ.get('SECRET_KEY','')
    if len(key)<32 or key.startswith(('CHANGE','CAMBIAR','VALOR_')):
        raise ValueError('Configurar SECRET_KEY aleatoria (mínimo 32 caracteres) en EasyPanel.')
    for variable in ('PERSONAL_VOICE_REFERENCE','PERSONAL_VOICE_TRANSCRIPT'):
        path=Path(os.environ[variable])
        if not path.is_file() or not os.access(path,os.R_OK):
            raise ValueError(f'Falta archivo privado legible: {variable}; montar /voice para UID 10001.')
    Path('/data/jobs').mkdir(parents=True,exist_ok=True)

def main():
    validate()
    path=Path(os.environ['PERSONAL_VOICE_MODEL'])
    marker=path/'locutor-model-revision.json'
    ready=False
    if marker.exists():
        ready=json.loads(marker.read_text()).get('revision')==REVISION and (path/'config.json').is_file()
    if not ready:
        print('Descargando modelo público al volumen persistente; puede tardar.',flush=True)
        subprocess.run([sys.executable,'-m','scripts.download_cpu_model'],check=True)
    report=Path('/data/benchmark/informe.json')
    if os.environ.get('BENCHMARK_ON_FIRST_START','false').lower()=='true' and not report.exists():
        print('Ejecutando prueba CPU antes de cargar el servidor web.',flush=True)
        subprocess.run([sys.executable,'-m','scripts.benchmark_cpu'],check=True,timeout=1800)
    print('Modelo preparado. Iniciando la aplicación.',flush=True)
if __name__=='__main__':main()
