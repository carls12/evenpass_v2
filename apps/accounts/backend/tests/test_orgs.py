from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import update

from conftest import API, bearer, signup
import db
import main


def expire_trial(email):
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.email == email).values(trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1)))


def create_icc(admin, **extra):
    body = {'name': 'ICC Berlin', 'slug': 'icc', 'color': '#aa3300', 'apps': ['eventpass', 'bodyofchrist'], **extra}
    r = TestClient(main.app).post(f'{API}/admin/orgs', json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_only_platform_admin_creates_orgs_and_addresses_are_checked(admin):
    anna = bearer(signup(TestClient(main.app))['token'])
    c = TestClient(main.app)
    assert c.post(f'{API}/admin/orgs', json={'name': 'X Y', 'slug': 'xy'}, headers=anna).status_code == 403
    assert c.post(f'{API}/admin/orgs', json={'name': 'Admin', 'slug': 'admin'}, headers=admin).status_code == 422  # reserved
    assert c.post(f'{API}/admin/orgs', json={'name': 'Bad', 'slug': 'Bad Name!'}, headers=admin).status_code == 422
    create_icc(admin)
    assert c.post(f'{API}/admin/orgs', json={'name': 'Other', 'slug': 'icc'}, headers=admin).status_code == 409
    page = c.get(f'{API}/orgs/icc/public').json()
    assert page['name'] == 'ICC Berlin' and page['apps'] == ['eventpass', 'bodyofchrist'] and 'join_code' not in page


def test_invited_admin_joins_on_registration_and_members_get_pro(admin):
    org = create_icc(admin, admin_email='pastor@icc.example')
    assert org['invite']['status'] == 'invited'
    pastor = signup(TestClient(main.app), 'pastor@icc.example', 'pastor-pass-1', 'Pastor')
    assert pastor['user']['organisations'][0] == {'slug': 'icc', 'name': 'ICC Berlin', 'role': 'admin', 'color': '#aa3300'}
    expire_trial('pastor@icc.example')
    me = TestClient(main.app).get(f'{API}/me', headers=bearer(pastor['token'])).json()
    assert me['pro'] and me['pro_source'] == 'organisation'

    # the church admin manages the page: join link for members
    p = TestClient(main.app)
    detail = p.get(f'{API}/orgs/icc', headers=bearer(pastor['token'])).json()
    assert detail['can_manage'] and detail['members'][0]['email'] == 'pastor@icc.example'
    member = signup(TestClient(main.app), 'grace@example.org', 'grace-pass-1', 'Grace')
    m = TestClient(main.app)
    assert m.post(f'{API}/orgs/icc/join', json={'code': 'wrong'}, headers=bearer(member['token'])).status_code == 403
    assert m.post(f'{API}/orgs/icc/join', json={'code': detail['join_code']}, headers=bearer(member['token'])).status_code == 200
    assert m.get(f'{API}/orgs/icc', headers=bearer(member['token'])).json()['can_manage'] is False
    assert m.post(f'{API}/orgs/icc/invites', json={'email': 'x@example.org'}, headers=bearer(member['token'])).status_code == 403


def test_plan_end_seats_and_last_admin(admin):
    create_icc(admin, seats=1, admin_email='pastor@icc.example')
    pastor = signup(TestClient(main.app), 'pastor@icc.example', 'pastor-pass-1', 'Pastor')
    code = TestClient(main.app).get(f'{API}/orgs/icc', headers=bearer(pastor['token'])).json()['join_code']
    late = signup(TestClient(main.app), 'late@example.org', 'late-pass-11', 'Late')
    assert TestClient(main.app).post(f'{API}/orgs/icc/join', json={'code': code}, headers=bearer(late['token'])).status_code == 409  # full
    me = TestClient(main.app).get(f'{API}/me', headers=bearer(pastor['token'])).json()
    pid = me['id']
    assert TestClient(main.app).delete(f'{API}/orgs/icc/members/{pid}', headers=bearer(pastor['token'])).status_code == 409  # last admin
    # the platform admin switches the plan to free: membership stays, Pro from the church ends
    expire_trial('pastor@icc.example')
    assert TestClient(main.app).patch(f'{API}/admin/orgs/icc', json={'plan': 'free'}, headers=admin).json()['pro_active'] is False
    me = TestClient(main.app).get(f'{API}/me', headers=bearer(pastor['token'])).json()
    assert not me['pro'] and me['organisations'][0]['slug'] == 'icc'
    listed = TestClient(main.app).get(f'{API}/admin/orgs', headers=admin).json()
    assert listed[0]['members'] == 1 and listed[0]['seats'] == 1
