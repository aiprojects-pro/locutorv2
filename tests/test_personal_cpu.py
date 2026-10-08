from contextlib import nullcontext
from types import SimpleNamespace
import sys,json
import numpy as np
import pytest
from app.config import Settings
from app.tts.personal_cpu import PersonalCPUVoice

def settings(tmp_path):
    model=tmp_path/'model';model.mkdir()
    (model/'config.json').write_text(json.dumps({'tts_model_type':'base'}))
    ref=tmp_path/'ref.wav';ref.write_bytes(b'fixture')
    transcript=tmp_path/'ref.txt';transcript.write_text('Referencia de prueba.')
    return Settings(personal_voice_model=model,personal_voice_reference=ref,
                    personal_voice_transcript=transcript,personal_voice_backend='torch_cpu')

def test_cpu_adapter_loads_offline_cpu_and_reuses_reference(monkeypatch,tmp_path):
    s=settings(tmp_path);calls=[]
    class Model:
        @staticmethod
        def from_pretrained(path,**kw):calls.append(('load',kw));return Model()
        def create_voice_clone_prompt(self,**kw):calls.append(('prompt',kw));return ['cached']
        def generate_voice_clone(self,**kw):calls.append(('generate',kw));return [np.ones(2400)*.1],24000
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(float32='float32',set_num_threads=lambda n:None,inference_mode=nullcontext))
    monkeypatch.setitem(sys.modules,'qwen_tts',SimpleNamespace(Qwen3TTSModel=Model))
    voice=PersonalCPUVoice(s)
    try:
        assert voice.generate('Texto uno.',1).shape==(2400,)
        voice.generate('Texto dos.',1)
        assert calls[0][1]=={'device_map':'cpu','dtype':'float32','attn_implementation':'eager','local_files_only':True}
        assert len([c for c in calls if c[0]=='prompt'])==1
        assert calls[-1][1]['voice_clone_prompt']==['cached']
        assert calls[-1][1]['temperature']==.6
        with pytest.raises(ValueError):voice.generate('Texto',0)
        voice.model.generate_voice_clone=lambda **kw:([np.array([np.nan])],24000)
        with pytest.raises(ValueError):voice.generate('Texto',1)
    finally:voice.close()

def test_cpu_rejects_mlx_weights_before_import(tmp_path):
    s=settings(tmp_path)
    (s.personal_voice_model/'config.json').write_text(json.dumps({'tts_model_type':'base','quantization':{'bits':8}}))
    with pytest.raises(ValueError,match='original'):PersonalCPUVoice(s)

def test_registry_selects_cpu_without_loading_mlx(monkeypatch,tmp_path):
    from app.tts.engine import VoiceRegistry,Voice
    import app.tts.personal_cpu as mod
    fake=SimpleNamespace(sample_rate=24000,close=lambda:None)
    monkeypatch.setattr(mod,'PersonalCPUVoice',lambda s:fake)
    reg=VoiceRegistry(settings(tmp_path),[Voice('personal','Mi voz',tmp_path,0,'personal')],'personal')
    reg.load()
    assert reg._personal is fake
    assert reg.sample_rate_for('personal')==24000
    reg.close()
