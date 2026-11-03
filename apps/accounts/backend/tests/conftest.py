import os, sys, tempfile
from pathlib import Path

import pytest

# Isolated database: SQLite locally, PostgreSQL in CI when ACCOUNTS_DATABASE_URL is set.
TMP = Path(tempfile.mkdtemp(prefix='accounts-test-'))
os.environ.setdefault('ACCOUNTS_DATABASE_URL', f"sqlite:///{(TMP / 'test.sqlite3').as_posix()}")
os.environ.update({
    'ACCOUNTS_ENV': 'test',
    'CMGI_ADMIN_EMAILS': 'admin@example.org',
    'ACCOUNTS_INTERNAL_KEY': 'internal-test-key-0123456789abcdef',
    'ACCOUNTS_LOGIN_LIMIT': '5',
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
import db  # noqa: E402
import main  # noqa: E402

API = '/api/accounts'
INTERNAL = {'X-Internal-Key': 'internal-test-key-0123456789abcdef'}


@pytest.fixture(autouse=True)
def clean():
    main.failures.clear()
    with db.engine.begin() as c:
        for table in reversed(db.meta.sorted_tables): c.execute(table.delete())
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


class Outbox(list):
    def __call__(self, msg): self.append(msg)

    def link(self):
        import re
        body = next(p for p in self[-1].walk() if p.get_content_type() == 'text/plain').get_content()
        return re.search(r'https?://\S+', body).group(0)


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(main.mailer, 'SMTP_HOST', 'smtp.test')
    monkeypatch.setattr(main.mailer, 'MAIL_FROM', 'CMGI <accounts@example.org>')
    monkeypatch.setattr(main.mailer, 'deliver', box)
    return box


def signup(client, email='anna@example.org', password='secret-pass-1', name='Anna'):
    """Without mail the account is confirmed immediately (trial starts). Returns a fresh client session."""
    r = client.post(f'{API}/register', json={'email': email, 'password': password, 'name': name})
    assert r.status_code == 201, r.text
    return r.json()


def bearer(token): return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin(client):
    return bearer(signup(TestClient(main.app), 'admin@example.org', 'admin-pass-123', 'Admin')['token'])
