import sqlite3
from datetime import datetime, timedelta, timezone

from conftest import API, png_data_url
import main
import backup


def register(client, event, email='anna@example.org'):
    r = client.post(f'{API}/public/events/{event}/register',
                    json={'name': 'Anna Muster', 'email': email, 'answers': {'Gemeinde': 'CMGI'}})
    assert r.status_code == 201, r.text
    return r.json()


def gate_account(client, admin, event, can_add=False, username='anna.tor'):
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post(f'{API}/events/{event}/gate-users', headers=admin,
                    json={'display_name': 'Anna Eingang', 'username': username, 'expires_at': expires, 'can_add': can_add})
    assert r.status_code == 201, r.text
    creds = r.json()
    assert creds['display_name'] == 'Anna Eingang'
    login = client.post(f'{API}/gate/login', json={'username': creds['username'], 'password': creds['password']})
    assert login.status_code == 200, login.text
    return creds, {'Authorization': f"Bearer {login.json()['token']}"}


def test_health_on_both_prefixes(client):
    assert client.get(f'{API}/health').json() == {'ok': True}
    assert client.get('/api/health').json() == {'ok': True}  # legacy alias


def test_admin_endpoints_require_login(client, event):
    assert client.get(f'{API}/events').status_code == 401
    assert client.get(f'{API}/events', headers={'Authorization': 'Bearer nope'}).status_code == 401
    assert client.get(f'{API}/events/{event}/badges/a4.pdf').status_code == 401


def test_wrong_password_and_rate_limit(client):
    for _ in range(5):
        assert client.post(f'{API}/login', json={'password': 'wrong'}).status_code == 401
    assert client.post(f'{API}/login', json={'password': 'wrong'}).status_code == 429
    # A locked-out IP is refused even with the right password until the window passes.
    assert client.post(f'{API}/login', json={'password': 'test-admin-password'}).status_code == 429


def test_gate_login_rate_limit(client):
    for _ in range(5):
        assert client.post(f'{API}/gate/login', json={'username': 'x', 'password': 'y'}).status_code == 401
    assert client.post(f'{API}/gate/login', json={'username': 'x', 'password': 'y'}).status_code == 429


def test_create_event_validation(client, admin):
    bad = {'title': 'X2', 'location': 'Ort', 'start_date': '2026-08-17', 'end_date': '2026-08-15'}
    assert client.post(f'{API}/events', json=bad, headers=admin).status_code == 422


def test_event_listed_and_public(client, admin, event):
    assert any(e['id'] == event for e in client.get(f'{API}/events', headers=admin).json())
    pub = client.get(f'{API}/public/events/{event}').json()
    assert pub['title'] == 'FOUND 2026' and pub['fields'][0]['label'] == 'Gemeinde'


def test_registration_rules(client, event):
    r = client.post(f'{API}/public/events/{event}/register', json={'name': 'Bob', 'email': 'bob@example.org'})
    assert r.status_code == 422  # required custom field missing
    register(client, event, 'dup@example.org')
    r = client.post(f'{API}/public/events/{event}/register',
                    json={'name': 'Dup', 'email': 'DUP@example.org', 'answers': {'Gemeinde': 'x'}})
    assert r.status_code == 409


def form_event(client, admin):
    fields = [{'label': 'Gemeinde', 'required': True},
              {'label': 'Größe', 'type': 'select', 'options': ['S', 'M', 'L', ' ', 'M'], 'required': True},
              {'label': 'Dienste', 'type': 'checkbox', 'options': ['Musik', 'Technik', 'Küche']},
              {'label': 'Alter', 'type': 'number'},
              {'label': 'Anreise', 'type': 'date', 'help': 'Ankunftstag'}]
    r = client.post(f'{API}/events', headers=admin, json={'title': 'Camp', 'location': 'Ort', 'start_date': '2026-08-15', 'end_date': '2026-08-17', 'fields': fields})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_typed_fields_are_cleaned_and_validated(client, admin):
    event = form_event(client, admin)
    fields = client.get(f'{API}/public/events/{event}').json()['fields']
    assert fields[1]['options'] == ['S', 'M', 'L'] and fields[0]['type'] == 'text' and fields[4]['help'] == 'Ankunftstag'
    url = f'{API}/public/events/{event}/register'
    base = {'name': 'Anna', 'email': 'a@example.org'}
    for bad in ({'Gemeinde': 'X', 'Größe': 'XXL'}, {'Gemeinde': 'X', 'Größe': 'S', 'Dienste': ['Tanz']},
                {'Gemeinde': 'X', 'Größe': 'S', 'Alter': 'zwölf'}, {'Gemeinde': 'X', 'Größe': 'S', 'Anreise': '15.08.'},
                {'Gemeinde': 'X', 'Größe': ['S', 'M']}, {'Gemeinde': 'X'}):
        assert client.post(url, json={**base, 'answers': bad}).status_code == 422, bad
    ok = client.post(url, json={**base, 'answers': {'Gemeinde': 'CMGI', 'Größe': 'M', 'Dienste': ['Küche', 'Musik'], 'Alter': '', 'Anreise': '2026-08-15'}})
    assert ok.status_code == 201, ok.text
    stored = client.get(f'{API}/events/{event}/participants', headers=admin).json()[0]['answers']
    assert stored == {'Gemeinde': 'CMGI', 'Größe': 'M', 'Dienste': 'Musik, Küche', 'Anreise': '2026-08-15'}


def test_choice_field_needs_options_and_unique_labels(client, admin):
    body = {'title': 'Camp', 'location': 'Ort', 'start_date': '2026-08-15', 'end_date': '2026-08-17'}
    assert client.post(f'{API}/events', headers=admin, json={**body, 'fields': [{'label': 'Größe', 'type': 'radio'}]}).status_code == 422
    assert client.post(f'{API}/events', headers=admin, json={**body, 'fields': [{'label': 'A'}, {'label': ' a '}]}).status_code == 422
    assert client.post(f'{API}/events', headers=admin, json={**body, 'fields': [{'label': 'A', 'type': 'slider'}]}).status_code == 422


def test_fields_can_be_edited_and_answers_exported(client, admin, event):
    register(client, event, 'csv@example.org')
    r = client.put(f'{API}/events/{event}/fields', headers=admin, json={'fields': [{'label': 'Telefon', 'type': 'phone'}]})
    assert r.status_code == 200 and r.json()['fields'][0]['type'] == 'phone'
    assert client.put(f'{API}/events/{event}/fields', json={'fields': []}).status_code == 401
    assert client.get(f'{API}/public/events/{event}').json()['fields'][0]['label'] == 'Telefon'
    client.post(f'{API}/public/events/{event}/register', json={'name': '=HYPERLINK("x")', 'email': 'f@example.org', 'answers': {'Telefon': '+49 170 1'}})
    csv = client.get(f'{API}/events/{event}/participants.csv', headers=admin)
    assert csv.status_code == 200 and 'text/csv' in csv.headers['content-type']
    lines = csv.text.lstrip('﻿').splitlines()
    assert lines[0] == 'Name;E-Mail;Kategorie;Verpflegung;Telefon;Gemeinde;Registriert am;Eingecheckt'
    assert 'CMGI' in lines[1]  # answer to the removed field is still exported
    assert lines[2].startswith('"\'=HYPERLINK') and "'+49 170 1" in lines[2]
    assert client.get(f'{API}/events/{event}/participants.csv').status_code == 401


def test_qr_and_badge_pdf(client, event):
    secret = register(client, event)['badge_secret']
    qr = client.get(f'{API}/public/badge/{secret}/qr.png')
    assert qr.status_code == 200 and qr.content[:8] == b'\x89PNG\r\n\x1a\n'
    pdf = client.get(f'{API}/public/badge/{secret}/pdf')
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    assert client.get(f'{API}/public/badge/unknown/pdf').status_code == 404


def test_a4_sheet(client, admin, event):
    assert client.get(f'{API}/events/{event}/badges/a4.pdf', headers=admin).status_code == 400  # no participants yet
    for i in range(5): register(client, event, f'p{i}@example.org')
    r = client.get(f'{API}/events/{event}/badges/a4.pdf', headers=admin)
    assert r.status_code == 200 and r.content.startswith(b'%PDF')


def pages(pdf):
    import re
    return len(re.findall(rb'/Type /Page[^s]', pdf))


def test_a4_sheet_selected_participants(client, admin, event):
    ids = [register(client, event, f's{i}@example.org')['participant_id'] for i in range(5)]
    url = f'{API}/events/{event}/badges/a4.pdf'
    everyone = client.get(url, headers=admin)
    two = client.post(url, headers=admin, json={'participant_ids': ids[:2]})
    assert two.status_code == 200 and two.content.startswith(b'%PDF')
    assert pages(two.content) == 1 and pages(everyone.content) == 2  # 85x130 mm -> 4 per A4 sheet
    assert pages(client.post(url, headers=admin, json={'participant_ids': ids}).content) == 2
    assert client.post(url, json={'participant_ids': ids[:1]}).status_code == 401
    assert client.post(url, headers=admin, json={'participant_ids': []}).status_code == 422
    # Participants of another event cannot be smuggled into the sheet.
    other = client.post(f'{API}/events', headers=admin, json={'title': 'Other', 'location': 'X1', 'start_date': '2026-01-01', 'end_date': '2026-01-01'}).json()['id']
    stranger = client.post(f'{API}/events/{other}/participants/manual', headers=admin, json={'name': 'Stranger', 'category': 'Guest'}).json()['participant_id']
    assert client.post(url, headers=admin, json={'participant_ids': [ids[0], stranger]}).status_code == 400


def test_registration_qr_and_poster(client, event):
    link = f'https://cmgi-apps.de/eventpass/register/{event}'
    qr = client.get(f'{API}/public/events/{event}/registration-qr.png', params={'url': link})
    assert qr.status_code == 200 and qr.content[:8] == b'\x89PNG\r\n\x1a\n'
    poster = client.get(f'{API}/public/events/{event}/registration-poster.pdf', params={'url': link})
    assert poster.status_code == 200 and poster.content.startswith(b'%PDF') and pages(poster.content) == 1
    for bad in ('https://evil.example/phish', 'javascript:alert(1)//register/' + event, f'https://x.de/register/{event}x'):
        assert client.get(f'{API}/public/events/{event}/registration-qr.png', params={'url': bad}).status_code == 400
    assert client.get(f'{API}/public/events/unknown/registration-qr.png', params={'url': 'https://x.de/register/unknown'}).status_code == 404


def test_checkin_tolerates_scanner_whitespace(client, admin, event):
    secret = register(client, event, 'ws@example.org')['badge_secret']
    r = client.post(f'{API}/events/{event}/checkin', headers=admin, json={'qr_value': f' EVP:{secret}\n', 'day': '2026-08-15'})
    assert r.json()['status'] == 'checked_in'


def test_manual_participant_without_email(client, admin, event):
    r = client.post(f'{API}/events/{event}/participants/manual', headers=admin, json={'name': 'Pastor Joseph', 'category': 'Pastor'})
    assert r.status_code == 201
    people = client.get(f'{API}/events/{event}/participants', headers=admin).json()
    assert people[0]['name'] == 'Pastor Joseph' and people[0]['email'].endswith('@eventpass.invalid')


def test_badge_settings_and_images_persist(client, admin, event):
    settings = {'badge_width_mm': 90, 'badge_height_mm': 120, 'badge_heading': 'Impact Camp', 'badge_accent': 'Gold',
                'badge_date_label': '15.–17.08.', 'badge_location_label': 'BS', 'badge_qr_label': 'SCAN'}
    assert client.patch(f'{API}/events/{event}/badge-settings', headers=admin, json=settings).status_code == 200
    stored = client.get(f'{API}/public/events/{event}').json()
    assert {k: stored[k] for k in settings} == settings
    for kind in ('background', 'logo'):
        assert client.post(f'{API}/events/{event}/badge-image/{kind}', headers=admin, json={'data_url': png_data_url()}).status_code == 200
        assert client.get(f'{API}/public/events/{event}/badge-image/{kind}').status_code == 200
    assert client.post(f'{API}/events/{event}/badge-image/background', headers=admin, json={'data_url': 'data:image/png;base64,AAAA'}).status_code == 422
    # Badge PDF still renders with the custom images.
    secret = register(client, event, 'img@example.org')['badge_secret']
    assert client.get(f'{API}/public/badge/{secret}/pdf').content.startswith(b'%PDF')


def test_admin_checkin_once_per_day(client, admin, event):
    secret = register(client, event)['badge_secret']
    first = client.post(f'{API}/events/{event}/checkin', headers=admin, json={'qr_value': 'EVP:' + secret, 'day': '2026-08-15'}).json()
    again = client.post(f'{API}/events/{event}/checkin', headers=admin, json={'qr_value': 'EVP:' + secret, 'day': '2026-08-15'}).json()
    next_day = client.post(f'{API}/events/{event}/checkin', headers=admin, json={'qr_value': 'EVP:' + secret, 'day': '2026-08-16'}).json()
    assert (first['status'], again['status'], next_day['status']) == ('checked_in', 'duplicate', 'checked_in')
    att = client.get(f'{API}/events/{event}/attendance', headers=admin).json()
    assert att['registered'] == 1 and att['present_unique'] == 1 and len(att['checkins']) == 2
    stats = client.get(f'{API}/events/{event}/stats', headers=admin).json()
    assert [d['count'] for d in stats['checkins_by_day']] == [1, 1]
    assert client.post(f'{API}/events/{event}/checkin', headers=admin, json={'qr_value': 'garbage'}).status_code == 400


def test_gate_staff_permissions(client, admin, event):
    other = client.post(f'{API}/events', headers=admin, json={'title': 'Other', 'location': 'X1', 'start_date': '2026-01-01', 'end_date': '2026-01-01'}).json()['id']
    secret = register(client, event)['badge_secret']
    other_secret = client.post(f'{API}/public/events/{other}/register', json={'name': 'Zed', 'email': 'zed@example.org'}).json()['badge_secret']
    creds, gate = gate_account(client, admin, event, can_add=False)
    assert 'password_hash' not in str(client.get(f'{API}/events/{event}/gate-users', headers=admin).json())
    assert client.post(f'{API}/gate/{event}/checkin', headers=gate, json={'qr_value': 'EVP:' + secret}).json()['status'] == 'checked_in'
    assert client.post(f'{API}/gate/{event}/checkin', headers=gate, json={'qr_value': 'EVP:' + other_secret}).status_code == 400
    assert client.get(f'{API}/gate/{other}/overview', headers=gate).status_code == 403
    assert client.post(f'{API}/gate/{event}/participants', headers=gate, json={'name': 'New Guest'}).status_code == 403
    assert client.get(f'{API}/events', headers=gate).status_code == 401  # gate token is not an admin token
    overview = client.get(f'{API}/gate/{event}/overview', headers=gate).json()
    assert overview['total'] == 1 and overview['checked_unique'] == 1 and overview['today'] == 1


def test_gate_staff_can_add_and_revoke(client, admin, event):
    creds, gate = gate_account(client, admin, event, can_add=True, username='ben.tor')
    added = client.post(f'{API}/gate/{event}/participants', headers=gate, json={'name': 'Walk-in Guest', 'category': 'Guest'})
    assert added.status_code == 201
    user_id = client.get(f'{API}/events/{event}/gate-users', headers=admin).json()[0]['id']
    assert client.post(f'{API}/events/{event}/gate-users/{user_id}/revoke', headers=admin).status_code == 200
    assert client.get(f'{API}/gate/{event}/overview', headers=gate).status_code == 401
    assert client.post(f'{API}/gate/login', json={'username': 'ben.tor', 'password': creds['password']}).status_code == 401


def test_gate_expiry_must_be_bounded(client, admin, event):
    far = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    r = client.post(f'{API}/events/{event}/gate-users', headers=admin, json={'display_name': 'Late', 'username': 'late', 'expires_at': far})
    assert r.status_code == 422


def test_data_is_on_disk(client, event):
    register(client, event, 'disk@example.org')
    conn = sqlite3.connect(main.DB)  # fresh connection = what a restart would see
    assert conn.execute('SELECT COUNT(*) FROM participants WHERE email=?', ('disk@example.org',)).fetchone()[0] == 1
    conn.close()


def test_backup_roundtrip(client, event, tmp_path):
    register(client, event, 'backup@example.org')
    snap = backup.backup_database(main.DB, tmp_path / 'b', main.ASSETS_DIR, label='test')
    assert backup.counts(snap / 'eventpass.sqlite3') == backup.counts(main.DB)


def test_init_backs_up_before_migration(tmp_path, monkeypatch):
    legacy = tmp_path / 'legacy.sqlite3'
    conn = sqlite3.connect(legacy)
    conn.execute('CREATE TABLE events(id TEXT PRIMARY KEY,title TEXT NOT NULL,location TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,fields TEXT NOT NULL,created_at TEXT NOT NULL)')
    conn.execute("INSERT INTO events VALUES ('e1','Old','Ort','2025-01-01','2025-01-01','[]','2025-01-01')")
    conn.commit(); conn.close()
    monkeypatch.setattr(main, 'DB', legacy)
    monkeypatch.setattr(main, 'BACKUP_DIR', tmp_path / 'backups')
    main.init()
    snaps = list((tmp_path / 'backups').glob('*-pre-migration'))
    assert len(snaps) == 1
    old_cols = {r[1] for r in sqlite3.connect(snaps[0] / 'eventpass.sqlite3').execute('PRAGMA table_info(events)')}
    new_cols = {r[1] for r in sqlite3.connect(legacy).execute('PRAGMA table_info(events)')}
    assert 'badge_width_mm' not in old_cols and 'badge_width_mm' in new_cols
    assert sqlite3.connect(legacy).execute('SELECT title FROM events').fetchone()[0] == 'Old'


def test_restore_keeps_safety_copy(tmp_path):
    live, old = tmp_path / 'live.sqlite3', tmp_path / 'old.sqlite3'
    for path, title in ((live, 'Current'), (old, 'Imported')):
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE events(id TEXT PRIMARY KEY, title TEXT)')
        conn.execute('INSERT INTO events VALUES (?, ?)', ('e1', title)); conn.commit(); conn.close()
    backup.restore(old, live, tmp_path / 'assets', tmp_path / 'backups')
    assert sqlite3.connect(live).execute('SELECT title FROM events').fetchone()[0] == 'Imported'
    safety = next((tmp_path / 'backups').glob('*-pre-restore'))
    assert sqlite3.connect(safety / 'eventpass.sqlite3').execute('SELECT title FROM events').fetchone()[0] == 'Current'
