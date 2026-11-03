from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import update

from conftest import API, INTERNAL, bearer, signup
import db
import main


def test_health(client):
    assert client.get(f'{API}/health').json()['ok'] is True


def test_register_signs_in_with_cookie_and_starts_trial_without_mail(client):
    data = signup(client)
    user = data['user']
    assert user['email'] == 'anna@example.org' and user['email_verified'] and not user['is_admin']
    assert user['pro'] and user['pro_source'] == 'trial' and user['ai_credit_seconds'] == 300
    trial_end = datetime.fromisoformat(user['trial_ends_at'])
    assert timedelta(days=13, hours=23) < trial_end - datetime.now(timezone.utc) <= timedelta(days=14)
    assert client.cookies.get('cmgi_session')
    me = client.get(f'{API}/me').json()  # cookie session, as in the browser
    assert me['id'] == user['id']
    assert TestClient(main.app).get(f'{API}/me', headers=bearer(data['token'])).json()['id'] == user['id']  # mobile app


def test_register_validation_and_duplicates(client):
    assert client.post(f'{API}/register', json={'email': 'no-at', 'password': 'secret-pass-1', 'name': 'X Y'}).status_code == 422
    assert client.post(f'{API}/register', json={'email': 'a@b.de', 'password': 'short', 'name': 'X Y'}).status_code == 422
    signup(client, 'Dup@Example.org')
    r = client.post(f'{API}/register', json={'email': 'dup@example.org ', 'password': 'secret-pass-1', 'name': 'Dup'})
    assert r.status_code == 409


def test_login_logout_and_throttle(client):
    signup(TestClient(main.app))
    c = TestClient(main.app)
    assert c.post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'wrong'}).status_code == 401
    r = c.post(f'{API}/login', json={'email': ' ANNA@example.org', 'password': 'secret-pass-1'})
    assert r.status_code == 200 and r.json()['user']['name'] == 'Anna'
    assert c.post(f'{API}/logout').status_code == 200
    assert c.get(f'{API}/me').status_code == 401
    for _ in range(5): c.post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'wrong'})
    assert c.post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'secret-pass-1'}).status_code == 429


def test_cross_site_requests_are_refused(client):
    r = client.post(f'{API}/register', json={'email': 'x@example.org', 'password': 'secret-pass-1', 'name': 'Xavier'},
                    headers={'Origin': 'https://evil.example'})
    assert r.status_code == 403
    r = client.post(f'{API}/register', json={'email': 'x@example.org', 'password': 'secret-pass-1', 'name': 'Xavier'},
                    headers={'Origin': 'http://testserver'})
    assert r.status_code == 201


def test_email_confirmation_starts_trial_once(client, outbox):
    data = signup(client)
    assert data['verification_sent'] and not data['user']['email_verified'] and not data['user']['pro']
    assert data['user']['ai_credit_seconds'] == 0
    link = outbox.link()
    assert '/api/accounts/verify?token=' in link
    r = client.get(link.split('testserver', 1)[1], follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/account?verify=ok'
    me = client.get(f'{API}/me').json()
    assert me['email_verified'] and me['pro_source'] == 'trial' and me['ai_credit_seconds'] == 300
    assert client.get(link.split('testserver', 1)[1], follow_redirects=False).headers['location'] == '/account?verify=invalid'
    assert client.get(f'{API}/me').json()['ai_credit_seconds'] == 300  # trial credit only once


def test_trial_expires(client):
    data = signup(client)
    with db.engine.begin() as c:
        c.execute(update(db.users).values(trial_ends_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    me = client.get(f'{API}/me').json()
    assert not me['pro'] and me['trial_used'] and me['pro_source'] is None


def test_password_reset_flow(client, outbox):
    signup(client)
    outbox.clear()
    assert TestClient(main.app).post(f'{API}/password/forgot', json={'email': 'nobody@example.org'}).json()['ok']
    assert not outbox  # no mail for unknown addresses, same answer
    TestClient(main.app).post(f'{API}/password/forgot', json={'email': 'anna@example.org'})
    token = outbox.link().split('token=')[1]
    assert client.post(f'{API}/password/reset', json={'token': token, 'password': 'brand-new-pass'}).status_code == 200
    assert client.get(f'{API}/me').status_code == 401  # all sessions ended
    assert client.post(f'{API}/password/reset', json={'token': token, 'password': 'another-pass-1'}).status_code == 400
    assert TestClient(main.app).post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'brand-new-pass'}).status_code == 200


def test_profile_and_password_change(client):
    signup(client)
    assert client.patch(f'{API}/me', json={'name': 'Anna Muster'}).json()['name'] == 'Anna Muster'
    other = TestClient(main.app)
    other.post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'secret-pass-1'})
    assert client.post(f'{API}/me/password', json={'current_password': 'nope', 'new_password': 'new-pass-123'}).status_code == 403
    assert client.post(f'{API}/me/password', json={'current_password': 'secret-pass-1', 'new_password': 'new-pass-123'}).status_code == 200
    assert client.get(f'{API}/me').status_code == 200 and other.get(f'{API}/me').status_code == 401


def test_internal_credit_booking_is_idempotent_and_never_negative(client):
    uid = signup(client)['user']['id']
    body = {'user_id': uid, 'seconds': 200, 'ref': 'sermon:s1:0'}
    assert client.post(f'{API}/internal/credits/consume', json=body).status_code == 403
    assert client.post(f'{API}/internal/credits/consume', json=body, headers={'X-Internal-Key': 'wrong'}).status_code == 403
    assert client.post(f'{API}/internal/credits/consume', json=body, headers=INTERNAL).json()['ai_credit_seconds'] == 100
    assert client.post(f'{API}/internal/credits/consume', json=body, headers=INTERNAL).json()['duplicate'] is True
    r = client.post(f'{API}/internal/credits/consume', json={**body, 'ref': 'sermon:s1:1'}, headers=INTERNAL)
    assert r.status_code == 402
    assert client.post(f'{API}/internal/credits/refund', json={**body, 'ref': 'refund:sermon:s1:0'}, headers=INTERNAL).json()['ai_credit_seconds'] == 300
    assert client.post(f'{API}/internal/credits/refund', json={**body, 'ref': 'refund:sermon:s1:0'}, headers=INTERNAL).json()['ai_credit_seconds'] == 300


def test_admin_is_defined_by_config_only(client, admin):
    assert client.get(f'{API}/me', headers=admin).json()['is_admin'] is True
    user = bearer(signup(TestClient(main.app))['token'])
    assert client.get(f'{API}/admin/users', headers=user).status_code == 403
    assert client.get(f'{API}/admin/users').status_code == 401


def test_admin_grants_and_revokes_pro(client, admin):
    data = signup(TestClient(main.app))
    uid, user = data['user']['id'], bearer(data['token'])
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == uid).values(trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1)))
    assert not client.get(f'{API}/me', headers=user).json()['pro']
    listed = client.get(f'{API}/admin/users', params={'q': 'ANNA'}, headers=admin).json()
    assert [u['id'] for u in listed] == [uid]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert client.post(f'{API}/admin/users/{uid}/pro', json={'until': past}, headers=admin).status_code == 422
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = client.post(f'{API}/admin/users/{uid}/pro', json={'until': until, 'note': 'Pastor'}, headers=admin).json()
    assert r['pro'] and r['pro_source'] == 'grant'
    r = client.post(f'{API}/admin/users/{uid}/pro', json={'until': None, 'note': 'Lifetime'}, headers=admin).json()
    assert r['pro_until'] is None  # no end date wins
    detail = client.get(f'{API}/admin/users/{uid}', headers=admin).json()
    assert len(detail['grants']) == 2 and detail['grants'][0]['granted_by'] == 'admin@example.org'
    assert not client.delete(f'{API}/admin/users/{uid}/pro', headers=admin).json()['pro']
    overview = client.get(f'{API}/admin/overview', headers=admin).json()
    assert overview['users'] == 2 and overview['pro'] == 1  # the admin's own trial


def test_admin_credits_disable_and_reset_link(client, admin):
    data = signup(TestClient(main.app))
    uid, user = data['user']['id'], bearer(data['token'])
    assert client.post(f'{API}/admin/users/{uid}/credits', json={'minutes': 60, 'note': 'Gift'}, headers=admin).json()['ai_credit_seconds'] == 3900
    assert client.post(f'{API}/admin/users/{uid}/disable', json={'disabled': True}, headers=admin).json()['disabled']
    assert client.get(f'{API}/me', headers=user).status_code == 401
    assert TestClient(main.app).post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'secret-pass-1'}).status_code == 403
    client.post(f'{API}/admin/users/{uid}/disable', json={'disabled': False}, headers=admin)
    link = client.post(f'{API}/admin/users/{uid}/reset-link', headers=admin).json()['link']
    token = link.split('token=')[1]
    assert TestClient(main.app).post(f'{API}/password/reset', json={'token': token, 'password': 'given-by-admin'}).status_code == 200
    admin_id = client.get(f'{API}/me', headers=admin).json()['id']
    assert client.post(f'{API}/admin/users/{admin_id}/disable', json={'disabled': True}, headers=admin).status_code == 422


def test_internal_user_lookup(client):
    uid = signup(client)['user']['id']
    assert client.get(f'{API}/internal/users/{uid}').status_code == 403
    data = client.get(f'{API}/internal/users/{uid}', headers=INTERNAL).json()
    assert data['id'] == uid and data['pro'] is True
    assert client.get(f'{API}/internal/users/unknown', headers=INTERNAL).status_code == 404


def test_internal_user_by_email(client):
    uid = signup(client, 'Mia@Example.org')['user']['id']
    assert client.get(f'{API}/internal/users/by-email', params={'email': 'mia@example.org'}).status_code == 403
    r = client.get(f'{API}/internal/users/by-email', params={'email': ' MIA@example.org'}, headers=INTERNAL)
    assert r.json()['id'] == uid and r.json()['pro'] is True
    assert client.get(f'{API}/internal/users/by-email', params={'email': 'no@example.org'}, headers=INTERNAL).status_code == 404


def test_local_outbox_makes_password_reset_testable(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main.mailer, 'MAIL_OUTBOX', str(tmp_path))
    monkeypatch.setattr(main.mailer, 'SMTP_HOST', '')
    signup(client)
    assert client.post(f'{API}/password/forgot', json={'email': 'anna@example.org'}).json()['mail'] is True
    page = client.get(f'{API}/dev/outbox').text
    assert 'Reset your CMGI Apps password' in page
    token = page.split('reset-password?token=')[1].split('"')[0]
    assert client.post(f'{API}/password/reset', json={'token': token, 'password': 'brand-new-pass'}).status_code == 200
    assert TestClient(main.app).post(f'{API}/login', json={'email': 'anna@example.org', 'password': 'brand-new-pass'}).status_code == 200
    monkeypatch.setattr(main.mailer, 'SMTP_HOST', 'smtp.example.org')
    monkeypatch.setattr(main.mailer, 'MAIL_FROM', 'x@example.org')
    assert client.get(f'{API}/dev/outbox').status_code == 404  # real mail configured: no outbox


def google_flow(client, monkeypatch, profile, next_path='/eventpass/'):
    monkeypatch.setattr(main.google, 'CLIENT_ID', 'cid'); monkeypatch.setattr(main.google, 'CLIENT_SECRET', 'secret')
    monkeypatch.setattr(main.google, 'fetch_profile', lambda code, redirect: profile)
    start = client.get(f'{API}/google/start', params={'next': next_path}, follow_redirects=False)
    assert start.status_code == 303 and start.headers['location'].startswith('https://accounts.google.com/')
    state = start.headers['location'].split('state=')[1].split('&')[0]
    return client.get(f'{API}/google/callback', params={'code': 'abc', 'state': state}, follow_redirects=False)


def test_google_off_until_configured(client):
    assert client.get(f'{API}/providers').json() == {'google': False}
    assert client.get(f'{API}/google/start', follow_redirects=False).status_code == 404


def test_google_creates_account_with_trial_and_signs_in(client, monkeypatch):
    r = google_flow(client, monkeypatch, {'sub': 'g-1', 'email': 'grace@example.org', 'email_verified': True, 'name': 'Grace'})
    assert r.status_code == 303 and r.headers['location'] == '/eventpass/'
    me = client.get(f'{API}/me').json()
    assert me['email'] == 'grace@example.org' and me['pro_source'] == 'trial' and me['email_verified']
    # second visit finds the same account through the Google id, even if the Google email changed
    again = google_flow(TestClient(main.app), monkeypatch, {'sub': 'g-1', 'email': 'new@example.org', 'email_verified': True, 'name': 'Grace'})
    assert again.status_code == 303
    with db.engine.connect() as c: assert c.execute(db.users.select()).fetchall().__len__() == 1


def test_google_links_existing_account_and_rejects_bad_state(client, monkeypatch):
    signup(client)
    other = TestClient(main.app)
    r = google_flow(other, monkeypatch, {'sub': 'g-2', 'email': 'anna@example.org', 'email_verified': True, 'name': 'Anna'}, '//evil.example')
    assert r.headers['location'] == '/account'  # foreign redirect targets are ignored
    assert other.get(f'{API}/me').json()['email'] == 'anna@example.org'
    bad = TestClient(main.app).get(f'{API}/google/callback', params={'code': 'x', 'state': 'forged'}, follow_redirects=False)
    assert bad.headers['location'] == '/login?error=google'
    unverified = google_flow(TestClient(main.app), monkeypatch, {'sub': 'g-3', 'email': 'x@example.org', 'email_verified': False, 'name': 'X'})
    assert unverified.headers['location'] == '/login?error=google_unverified'
    # a Google-only account has no password that could be guessed
    google_flow(TestClient(main.app), monkeypatch, {'sub': 'g-4', 'email': 'g4@example.org', 'email_verified': True, 'name': 'G4'})
    assert TestClient(main.app).post(f'{API}/login', json={'email': 'g4@example.org', 'password': '!google'}).status_code == 401
