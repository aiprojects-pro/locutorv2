"""Persistent, owner-scoped script drafts. Single-process deployment, like JobManager."""
from __future__ import annotations
from contextlib import contextmanager
import difflib
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path


def changes(original: str, text: str) -> dict:
    numbers = set(re.findall(r'\b\d+(?:[.,/]\d+)*\b', original))
    present = set(re.findall(r'\b\d+(?:[.,/]\d+)*\b', text))
    missing = sorted(numbers - present)
    quotes = re.findall(r'«([^»]{8,1000})»|“([^”]{8,1000})”|"([^"\n]{8,1000})"', original)
    changed_quotes = [next(x for x in group if x) for group in quotes
                      if next(x for x in group if x) not in text]
    # Line-based comparison keeps a large document bounded and readable.
    diff = '\n'.join(difflib.unified_diff(original.splitlines(), text.splitlines(),
                                        fromfile='Original', tofile='Guion', lineterm=''))
    return {'changed': original != text, 'missing_numbers': missing,
            'changed_quotes': changed_quotes[:30], 'diff': diff[:120000]}


class ReviewError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class ReviewStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY, owner INTEGER NOT NULL, source TEXT NOT NULL,
                original TEXT NOT NULL, script TEXT NOT NULL, mode TEXT NOT NULL,
                version INTEGER NOT NULL, updated REAL NOT NULL,
                generated_version INTEGER, job_id TEXT, audio_options TEXT)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _row(db, review_id, owner):
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM reviews WHERE id=? AND owner=?', (review_id, owner)).fetchone()
        if row is None:
            raise ReviewError(404, 'Guion no encontrado.')
        return dict(row)

    def create(self, owner, source, original):
        review_id = uuid.uuid4().hex
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (review_id, owner, source, original, original, 'literal', 1, time.time(), None, None, None))
        return self.get(review_id, owner)

    def get(self, review_id, owner):
        with self.connect() as db:
            return self._row(db, review_id, owner)

    def list_for_user(self, owner):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(x) for x in db.execute(
                'SELECT id,source,mode,version,updated FROM reviews WHERE owner=? ORDER BY updated DESC LIMIT 30', (owner,))]

    def save(self, review_id, owner, version, mode, text):
        with self.lock, self.connect() as db:
            row = self._row(db, review_id, owner)
            if row['version'] != version:
                raise ReviewError(409, 'El guion cambió en otra ventana. Vuelve a abrirlo antes de guardar.')
            if mode == 'literal' and text != row['original']:
                raise ReviewError(422, 'Para cambiar el texto, selecciona Versión para escuchar.')
            db.execute('UPDATE reviews SET script=?,mode=?,version=version+1,updated=? WHERE id=?',
                       (text, mode, time.time(), review_id))
        return self.get(review_id, owner)

    def generate(self, review_id, owner, version, jobs, voice, speed, music):
        # Serialize saves/submits; repeat submission of the same revision reuses its job.
        with self.lock, self.connect() as db:
            row = self._row(db, review_id, owner)
            if row['version'] != version:
                raise ReviewError(409, 'El guion cambió. Abre y revisa la última versión antes de generar.')
            if row['generated_version'] == version:
                if json.loads(row['audio_options']) != [voice, speed, music]:
                    raise ReviewError(409, 'Guarda una nueva revisión para generar con estas opciones de audio.')
                job = jobs.get(row['job_id'])
                if job is None:
                    raise ReviewError(409, 'Ese trabajo ya no está disponible. Guarda una nueva revisión para volver a generarlo.')
                return job
            job = jobs.create(owner, row['script'], row['source'], voice, speed, music)
            db.execute('UPDATE reviews SET generated_version=?,job_id=?,audio_options=? WHERE id=?', (version, job.id, json.dumps([voice, speed, music]), review_id))
            return job


def public_review(row):
    return {key: row[key] for key in ('id', 'source', 'original', 'script', 'mode', 'version', 'updated')} | {
        'comparison': changes(row['original'], row['script']), 'generated': row['generated_version'] == row['version'],
        'audio_options': json.loads(row['audio_options']) if row['generated_version'] == row['version'] else None}
