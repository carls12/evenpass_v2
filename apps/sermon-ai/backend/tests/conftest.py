import os, sys, tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix='sermon-test-'))
os.environ.update({
    'SERMON_ENV': 'test',
    'SERMON_DB_PATH': str(TMP / 'test.sqlite3'),
    'SERMON_AUDIO_DIR': str(TMP / 'audio'),
    'SERMON_ADMIN_PASSWORD': 'test-admin-password',
    'SERMON_LOGIN_LIMIT': '5',
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
import ai  # noqa: E402
import main  # noqa: E402

API = '/api/sermon-ai'

REPORT = {
    'title': 'Faith that moves', 'central_message': 'God is faithful.', 'summary': 'Para one.\n\nPara two.',
    'scripture_references': [{'reference': 'John 3:16', 'context': 'God’s love'}],
    'main_points': [{'heading': 'Trust', 'explanation': 'Trust God — même aujourd’hui, für alle.', 'scriptures': ['Prov 3:5']}],
    'key_quotes': ['Faith is a decision.'], 'applications': ['Pray daily'], 'prayer_points': ['For the city'],
    'discussion_questions': ['Where do you need trust?'], 'transcript_quality_note': '',
}


@pytest.fixture(scope='session')
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def offline_ai(monkeypatch):
    """No network: fake AI services and run background jobs synchronously."""
    calls = {'transcribe': [], 'report': [], 'translate': []}

    def transcribe(path, mime, language, previous_text=''):
        calls['transcribe'].append((path.name, mime, language, previous_text))
        return f'text of {path.name}'

    def report(transcript, meta, language):
        calls['report'].append(language)
        return {**REPORT, 'title': f'{REPORT["title"]} ({language})'}

    def translate(transcript, meta, language):
        calls['translate'].append(language)
        return f'translated to {language}\n\nsecond paragraph'

    monkeypatch.setattr(ai, 'transcribe', transcribe)
    monkeypatch.setattr(ai, 'generate_report', report)
    monkeypatch.setattr(ai, 'translate', translate)
    monkeypatch.setattr(main, 'start', lambda target, *args: target(*args))
    main.login_failures.clear()
    return calls


@pytest.fixture(scope='session')
def admin(client):
    token = client.post(f'{API}/login', json={'password': 'test-admin-password'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def sermon(client, admin):
    r = client.post(f'{API}/sermons', headers=admin, json={'title': 'Sunday service', 'preacher': 'Pastor Joseph', 'sermon_date': '2026-11-01', 'language': 'en'})
    assert r.status_code == 201, r.text
    return r.json()['id']


def upload(client, admin, sermon_id, idx, seq, data=b'audio', mime='audio/webm;codecs=opus'):
    return client.put(f'{API}/sermons/{sermon_id}/segments/{idx}/chunks/{seq}', content=data,
                      headers={**admin, 'Content-Type': mime})
