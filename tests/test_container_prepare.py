import json
from pathlib import Path
import pytest
from scripts import container_prepare as prepare

def test_rejects_missing_secret_and_voice(monkeypatch,tmp_path):
    monkeypatch.delenv('SECRET_KEY',raising=False)
    with pytest.raises(ValueError,match='SECRET_KEY'):prepare.validate()
    monkeypatch.setenv('SECRET_KEY','x'*48)
    monkeypatch.setenv('PERSONAL_VOICE_REFERENCE',str(tmp_path/'absent.wav'))
    with pytest.raises(ValueError,match='privado'):prepare.validate()

def test_first_start_download_and_benchmark_then_reuses(monkeypatch,tmp_path):
    model=tmp_path/'model';report=tmp_path/'benchmark/informe.json';calls=[]
    monkeypatch.setenv('PERSONAL_VOICE_MODEL',str(model))
    monkeypatch.setenv('BENCHMARK_ON_FIRST_START','true')
    monkeypatch.setattr(prepare,'validate',lambda:None)
    monkeypatch.setattr(prepare,'Path',lambda p:report if p=='/data/benchmark/informe.json' else Path(p))
    def run(command,**kw):
        calls.append(command[-1])
        if command[-1]=='scripts.download_cpu_model':
            model.mkdir()
            (model/'config.json').write_text('{}')
            (model/'locutor-model-revision.json').write_text(json.dumps({'revision':prepare.REVISION}))
        else:
            assert kw['timeout']==1800
            report.parent.mkdir();report.write_text('{}')
    monkeypatch.setattr(prepare.subprocess,'run',run)
    prepare.main();prepare.main()
    assert calls==['scripts.download_cpu_model','scripts.benchmark_cpu']

def test_download_failure_prevents_start(monkeypatch,tmp_path):
    monkeypatch.setattr(prepare,'validate',lambda:None)
    monkeypatch.setenv('PERSONAL_VOICE_MODEL',str(tmp_path/'model'))
    def fail(*a,**k):raise RuntimeError('download failed')
    monkeypatch.setattr(prepare.subprocess,'run',fail)
    with pytest.raises(RuntimeError,match='download failed'):prepare.main()
