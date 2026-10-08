import threading
from types import SimpleNamespace

from app.config import Settings
from app.jobs import Job, JobManager
import app.jobs as jobs


def test_progress_reports_export_and_stops_clock(monkeypatch, tmp_path):
    job = Job(id='test', user_id=1, source_name='doc')
    clock = [10.0]
    monkeypatch.setattr(jobs.time, 'monotonic', lambda: clock[0])
    def generate(*args):
        clock[0] = 15
        assert job.public()['stage'] == 'synthesizing'
        assert job.public()['progress'] == 0
        return [0.0]
    def export(*args, **kwargs):
        assert job.public()['stage'] == 'exporting'
        assert job.public()['download_url'] is None
    monkeypatch.setattr(jobs, 'assemble_mp3', export)
    engine = SimpleNamespace(generate=generate, sample_rate_for=lambda v: 24000)
    mgr = JobManager(Settings(work_dir=tmp_path), engine, SimpleNamespace(normalize=lambda t:t))
    try:
        mgr._run(job, 'Hola.', 'personal', 1)
        clock[0] = 99
        assert job.status == 'done'
        assert job.public()['elapsed_seconds'] == 5
        assert job.public()['download_url']
    finally:
        mgr.shutdown()


def test_timeout_cancels_queued_fragment(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    mgr = JobManager(Settings(work_dir=tmp_path, concurrency=1, per_chunk_timeout_s=.02),
                     SimpleNamespace(generate=lambda *a:calls.append(a)),
                     SimpleNamespace(normalize=lambda t:t))
    def occupy():
        entered.set()
        release.wait(5)
    mgr._chunk_pool.submit(occupy)
    assert entered.wait(2)
    job = Job(id='timeout', user_id=1, source_name='doc')
    try:
        mgr._run(job, 'Hola.', 'personal', 1)
        assert job.status == 'error'
        assert job.public()['stage'] == 'error'
        assert job.public()['download_url'] is None
    finally:
        release.set()
        mgr.shutdown()
    assert calls == []
