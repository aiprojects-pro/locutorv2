from types import SimpleNamespace
from io import BytesIO
import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import routes_web as web
from app.reviews import ReviewStore, ReviewError, changes
from app.security.csrf import issue_csrf_token


class Jobs:
    def __init__(self): self.items = {}; self.received = []
    def create(self, *args):
        self.received.append(args)
        job = SimpleNamespace(id=str(len(self.items)+1), public=lambda: {'id': str(len(self.items)), 'status': 'pending'})
        self.items[job.id] = job
        return job
    def get(self, key): return self.items.get(key)


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = FastAPI(); app.include_router(web.router)
    app.state.reviews = ReviewStore(tmp_path/'reviews.sqlite3')
    app.state.jobs = Jobs()
    app.state.engine = SimpleNamespace(resolve=lambda _:SimpleNamespace(key='personal'))
    app.dependency_overrides[web.require_user] = lambda: SimpleNamespace(id=1, username='uno')
    monkeypatch.setattr(web.tts_user_limiter, 'hit', lambda _: True)
    with TestClient(app) as client:
        token = issue_csrf_token(); client.cookies.set(web._settings.csrf_cookie_name, token)
        client.token = token
        yield client


def make_doc(text):
    doc = Document(); doc.add_paragraph(text); out = BytesIO(); doc.save(out); return out.getvalue()


def prepare(client, text='Artículo 43. «Una digna calidad de vida».'):
    result = client.post('/upload', data={'csrf_token': client.token}, files={'files': ('tema.docx',make_doc(text))})
    assert result.status_code == 201, result.text
    return result.json()


def test_upload_requires_review_and_store_survives_restart(client):
    draft = prepare(client)
    assert client.app.state.jobs.received == []
    assert draft['script'] == draft['original']
    restored = ReviewStore(client.app.state.reviews.path)
    assert restored.get(draft['id'],1)['original'] == draft['original']
    assert client.get('/reviews').json()[0]['id'] == draft['id']


def test_saved_script_is_exact_generation_source_and_original_immutable(client):
    draft = prepare(client)
    changed = 'El artículo 43 trata este asunto. Texto revisado por la usuaria.'
    res = client.put('/reviews/'+draft['id'],json={'csrf_token':client.token,'version':1,'mode':'adapted','text':changed})
    assert res.status_code == 200
    saved = res.json(); assert saved['original'] == draft['original']; assert saved['version'] == 2
    assert saved['comparison']['changed_quotes']
    payload={'version':2,'reviewed':False,'csrf_token':client.token,'voice':'personal','speed':.9,'music':'calma'}
    url=f"/reviews/{draft['id']}/generate"
    assert client.post(url,json=payload).status_code == 422
    payload['reviewed']=True
    result=client.post(url,json=payload); assert result.status_code == 202, result.text
    assert client.app.state.jobs.received[0][1] == changed
    assert client.post(url,json=payload).json()['id'] == result.json()['id']
    assert len(client.app.state.jobs.received)==1
    payload['music']='aire'; assert client.post(url,json=payload).status_code==409
    assert client.get(f"/reviews/{draft['id']}/download").text == changed


def test_owner_scope_on_every_review_route(client):
    draft=prepare(client)
    client.app.dependency_overrides[web.require_user]=lambda:SimpleNamespace(id=2)
    assert client.get('/reviews').json()==[]
    base='/reviews/'+draft['id']
    assert client.get(base).status_code==404
    assert client.get(base+'/download').status_code==404
    assert client.put(base,json={'version':1,'mode':'adapted','text':'Otro texto','csrf_token':client.token}).status_code==404
    assert client.post(base+'/generate',json={'version':1,'reviewed':True,'csrf_token':client.token}).status_code==404


def test_csrf_empty_size_and_stale_revisions(client,monkeypatch):
    draft=prepare(client); base='/reviews/'+draft['id']
    payload={'version':1,'mode':'adapted','text':'Guion nuevo.','csrf_token':'incorrecto'}
    assert client.put(base,json=payload).status_code==403
    assert client.post(base+'/generate',json={'version':1,'reviewed':True,'csrf_token':'incorrecto'}).status_code==403
    payload['csrf_token']=client.token
    payload['text']=' '; assert client.put(base,json=payload).status_code==422
    monkeypatch.setattr(web._settings,'max_input_chars',10)
    payload['text']='x'*11; assert client.put(base,json=payload).status_code==413
    payload['text']='Nuevo.'; assert client.put(base,json=payload).status_code==200
    assert client.put(base,json=payload).status_code==409
    assert client.post(base+'/generate',json={'version':1,'reviewed':True,'csrf_token':client.token}).status_code==409


def test_literal_cannot_be_silently_rewritten_and_invalid_options(client):
    draft=prepare(client);base='/reviews/'+draft['id']
    assert client.put(base,json={'version':1,'mode':'literal','text':'Cambio','csrf_token':client.token}).status_code==422
    assert client.post(base+'/generate',json={'version':1,'reviewed':True,'csrf_token':client.token,'music':'bad'}).status_code==400
    assert client.post(base+'/generate',json={'version':1,'reviewed':True,'csrf_token':client.token,'speed':0}).status_code==422
    assert not client.app.state.jobs.received


def test_missing_numbers_and_quotes_are_warnings_not_content_certification():
    found=changes('Artículo 43, año 1978. «Una digna calidad de vida».','Artículo cuarenta y tres, año 1978.')
    assert found['missing_numbers']==['43']
    assert found['changed_quotes']==['Una digna calidad de vida']
    assert found['changed']


def test_anonymous_requests_are_rejected(client,monkeypatch):
    client.app.dependency_overrides.clear()
    monkeypatch.setattr(web,'get_current_user',lambda _:None)
    assert client.get('/reviews').status_code==401
    assert client.post('/upload',data={'csrf_token':client.token},files={'files':('tema.docx',make_doc('Hola'))}).status_code==401


def test_upload_limits(client,monkeypatch):
    monkeypatch.setattr(web._settings,'max_upload_bytes',3)
    assert client.post('/upload',data={'csrf_token':client.token},files={'files':('tema.docx',b'too large')}).status_code==413
