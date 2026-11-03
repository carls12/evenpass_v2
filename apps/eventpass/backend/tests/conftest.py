import base64, io, os, sys, tempfile
from pathlib import Path

import pytest

# Isolated data directory: tests never touch the real eventpass.sqlite3.
TMP = Path(tempfile.mkdtemp(prefix='eventpass-test-'))
os.environ.update({
    'EVENTPASS_ENV': 'test',
    'EVENTPASS_DB_PATH': str(TMP / 'test.sqlite3'),
    'EVENTPASS_ASSETS_DIR': str(TMP / 'assets'),
    'EVENTPASS_BACKUP_DIR': str(TMP / 'backups'),
    'EVENTPASS_ADMIN_PASSWORD': 'test-admin-password',
    'EVENTPASS_LOGIN_LIMIT': '5',
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

API = '/api/eventpass'


@pytest.fixture(scope='session')
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_throttle():
    main.login_failures.clear()


@pytest.fixture(scope='session')
def admin(client):
    token = client.post(f'{API}/login', json={'password': 'test-admin-password'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def event(client, admin):
    body = {'title': 'FOUND 2026', 'location': 'Braunschweig', 'start_date': '2026-08-15', 'end_date': '2026-08-17',
            'fields': [{'label': 'Gemeinde', 'required': True}]}
    r = client.post(f'{API}/events', json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()['id']


@pytest.fixture
def live_event(client, admin):
    """Event running yesterday..tomorrow, for scans that use the server's current day."""
    from datetime import timedelta
    day = main.today()
    body = {'title': 'Live Camp', 'location': 'Braunschweig', 'start_date': str(day - timedelta(days=1)),
            'end_date': str(day + timedelta(days=1)), 'fields': [{'label': 'Gemeinde', 'required': True}]}
    r = client.post(f'{API}/events', json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()['id']


def png_data_url():
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (40, 60), '#3366cc').save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


class FakeAccounts:
    """Stands in for the CMGI accounts service: token -> account."""
    def __init__(self):
        self.by_token, self.by_id = {}, {}

    def add(self, token, uid, pro=True, is_admin=False, name='Organiser'):
        account = {'id': uid, 'email': f'{uid}@example.org', 'name': name, 'is_admin': is_admin, 'pro': pro,
                   'pro_source': 'trial' if pro else None, 'pro_until': None}
        self.by_token[token] = self.by_id[uid] = account
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    fake = FakeAccounts()
    monkeypatch.setattr(main.cmgi_auth, 'account_for_token', lambda token: fake.by_token.get(token) if token else None)
    monkeypatch.setattr(main.cmgi_auth, 'account_by_id', lambda uid: fake.by_id.get(uid))
    return fake
