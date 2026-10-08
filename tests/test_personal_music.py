import time
from types import SimpleNamespace
import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import Settings
from app.tts.personal import change_tempo
from app.tts.music import MUSIC, write_music
from app.tts.audio import assemble_mp3
from app.tts.engine import load_voices, VoiceRegistry
from app.jobs import Job, JobManager
from app.api import routes_web as web

def test_tempo_keeps_pitch():
    sr=24000
    out=change_tempo(.1*np.sin(2*np.pi*440*np.arange(sr*2)/sr),sr,.9)
    assert abs(len(out)/sr-2/.9)<.08
    frequencies=np.fft.rfftfreq(len(out),1/sr)
    assert abs(frequencies[np.argmax(abs(np.fft.rfft(out)))]-440)<2

def test_music_presets(tmp_path):
    signals=[]
    for key in MUSIC:
        path=tmp_path/f"{key}.wav";write_music(path,key,8000)
        a,sr=sf.read(path)
        assert sr==8000 and a.shape==(512000,2)
        assert -46<20*np.log10(np.sqrt(np.mean(a*a)))<-44
        signals.append(a)
    assert all(not np.array_equal(signals[0],x) for x in signals[1:])
    with pytest.raises(ValueError):write_music(tmp_path/"invalid.wav","../other")

def test_registry_opt_in(tmp_path):
    catalog=tmp_path/"voices.yaml";catalog.write_text("voices: []")
    settings=Settings(voices_config=catalog,personal_voice_enabled=True)
    voices,default=load_voices(settings)
    assert default=="personal" and voices[0].backend=="personal"
    registry=VoiceRegistry(settings,voices,default)
    assert registry.list_voices()==[{"key":"personal","label":"Mi voz","default":True}]

def test_mp3_pair(tmp_path):
    sr=24000;a=.1*np.sin(2*np.pi*250*np.arange(sr)/sr).astype(np.float32)
    assemble_mp3([a,a],sr,tmp_path/"voice.mp3",120,"128k","calma",tmp_path/"music.mp3")
    assert (tmp_path/"voice.mp3").stat().st_size>1000
    assert (tmp_path/"music.mp3").stat().st_size>1000
    assert not list(tmp_path.glob("*.wav"))

def test_job_pair_and_active_cleanup(tmp_path):
    settings=Settings(work_dir=tmp_path,chunk_max_chars=50)
    engine=SimpleNamespace(generate=lambda *args:np.ones(2400,dtype=np.float32)*.02,sample_rate_for=lambda _:24000)
    manager=JobManager(settings,engine,SimpleNamespace(normalize=lambda x:x))
    try:
        job=manager.create(1,"Texto de prueba.","tema.docx","personal",.9,"aire")
        deadline=time.monotonic()+10
        while job.status not in {"done","error"} and time.monotonic()<deadline:time.sleep(.05)
        assert job.status=="done",job.error
        assert job.mp3_path.exists() and job.music_mp3_path.exists()
        assert job.public()["music_download_url"].endswith("?variant=music")
        job.status="processing";job.created_at=0
        manager._cleanup_expired()
        assert manager.get(job.id) is job
    finally:manager.shutdown()

def test_download_permissions(tmp_path):
    p=tmp_path/"audio.mp3";p.write_bytes(b"audio")
    job=Job("j",1,"tema.pdf",status="done",mp3_path=p,music_mp3_path=p)
    app=FastAPI();app.include_router(web.router)
    app.state.jobs=SimpleNamespace(get=lambda _:job)
    app.dependency_overrides[web.require_user]=lambda:SimpleNamespace(id=2)
    with TestClient(app) as client:
        assert client.get("/jobs/j/download?variant=music").status_code==404
        app.dependency_overrides[web.require_user]=lambda:SimpleNamespace(id=1)
        for variant in ("voice","music"):
            res=client.get("/jobs/j/download?variant="+variant)
            assert res.status_code==200
            assert ".pdf.mp3" not in res.headers["content-disposition"]
        assert client.get("/jobs/j/download?variant=invalid").status_code==400
        job.music_mp3_path=None
        assert client.get("/jobs/j/download?variant=music").status_code==409

def test_dashboard(monkeypatch):
    app=FastAPI();app.include_router(web.router)
    app.state.jobs=SimpleNamespace(list_for_user=lambda _:[])
    app.state.engine=SimpleNamespace(list_voices=lambda:[{"key":"personal","label":"Mi voz","default":True}])
    monkeypatch.setattr(web,"get_current_user",lambda _:SimpleNamespace(id=1,username="prueba"))
    with TestClient(app) as client:
        text=client.get("/").text
        assert all(x in text for x in ["Mi voz","Calma","Aire","Sereno"])
        assert 'value="0.9" selected' in text
