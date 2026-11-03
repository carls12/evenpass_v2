import hashlib, hmac, json, time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from conftest import API, signup
import billing
import db
import main

SECRET = 'whsec_test'


@pytest.fixture
def stripe(monkeypatch):
    """Fake Stripe API: records calls, answers like Stripe."""
    calls = []
    subs = {}

    def call(method, path, data=None):
        calls.append((method, path, data or {}))
        if path == '/customers': return {'id': 'cus_1'}
        if path == '/checkout/sessions': return {'id': 'cs_1', 'url': 'https://checkout.stripe.test/cs_1'}
        if path == '/billing_portal/sessions': return {'url': 'https://billing.stripe.test/p_1'}
        if path.startswith('/subscriptions/'): return dict(subs[path.split('/')[-1]])
        raise AssertionError(path)

    monkeypatch.setattr(billing, 'SECRET_KEY', 'sk_test')
    monkeypatch.setattr(billing, 'WEBHOOK_SECRET', SECRET)
    monkeypatch.setattr(billing, 'PRO_PRICE', 'price_pro')
    monkeypatch.setattr(billing, 'PRO_LABEL', '4.99 € / month')
    monkeypatch.setattr(billing, 'PACKS', billing.parse_packs('60|price_60|9 €,300|price_300|39 €'))
    monkeypatch.setattr(billing, 'call', call)
    return calls, subs


def send(client, event, secret=SECRET, age=0):
    payload = json.dumps(event).encode()
    t = int(time.time()) - age
    sig = hmac.new(secret.encode(), f'{t}.'.encode() + payload, hashlib.sha256).hexdigest()
    return client.post(f'{API}/billing/webhook', content=payload, headers={'Stripe-Signature': f't={t},v1={sig}', 'Content-Type': 'application/json'})


def expire_trial(uid):
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == uid).values(trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1)))


def test_config_hides_prices_until_stripe_is_set_up(client):
    assert client.get(f'{API}/billing/config').json() == {'enabled': False, 'pro': False, 'pro_label': '', 'packs': []}
    signup(client)
    assert client.post(f'{API}/billing/checkout', json={'product': 'pro'}).status_code == 503


def test_parse_packs():
    assert billing.parse_packs(' 60|price_a|9 € , bad , 300|price_b ') == [
        {'minutes': 60, 'price': 'price_a', 'label': '9 €'}, {'minutes': 300, 'price': 'price_b', 'label': ''}]


def test_pro_checkout_and_subscription_webhook(client, stripe):
    calls, subs = stripe
    uid = signup(client)['user']['id']
    expire_trial(uid)
    assert client.get(f'{API}/billing/config').json()['packs'] == [{'minutes': 60, 'label': '9 €'}, {'minutes': 300, 'label': '39 €'}]
    r = client.post(f'{API}/billing/checkout', json={'product': 'pro'})
    assert r.json()['url'] == 'https://checkout.stripe.test/cs_1'
    session = next(d for m, p, d in calls if p == '/checkout/sessions')
    assert session['mode'] == 'subscription' and session['customer'] == 'cus_1' and session['client_reference_id'] == uid
    assert session['success_url'].endswith('/account?paid=pro')
    assert not client.get(f'{API}/me').json()['pro']  # nothing unlocked by the browser

    end = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    subs['sub_1'] = {'id': 'sub_1', 'customer': 'cus_1', 'status': 'active', 'items': {'data': [{'current_period_end': end}]}}
    event = {'type': 'checkout.session.completed', 'data': {'object': {'id': 'cs_1', 'mode': 'subscription', 'subscription': 'sub_1', 'metadata': {'user_id': uid}}}}
    assert send(client, event).status_code == 200
    me = client.get(f'{API}/me').json()
    assert me['pro'] and me['pro_source'] == 'subscription' and me['subscription']['status'] == 'active'
    assert client.post(f'{API}/billing/checkout', json={'product': 'pro'}).status_code == 409

    cancelled = {'type': 'customer.subscription.deleted', 'data': {'object': {**subs['sub_1'], 'status': 'canceled'}}}
    assert send(client, cancelled).status_code == 200  # found via the customer id
    assert not client.get(f'{API}/me').json()['pro']
    assert client.post(f'{API}/billing/portal').json()['url'] == 'https://billing.stripe.test/p_1'


def test_minute_package_is_booked_once(client, stripe):
    calls, _ = stripe
    uid = signup(client)['user']['id']
    assert client.post(f'{API}/billing/checkout', json={'product': 'minutes', 'minutes': 45}).status_code == 422
    client.post(f'{API}/billing/checkout', json={'product': 'minutes', 'minutes': 60})
    session = [d for m, p, d in calls if p == '/checkout/sessions'][-1]
    assert session['mode'] == 'payment' and session['line_items'][0]['price'] == 'price_60'
    paid = {'type': 'checkout.session.completed', 'data': {'object': {'id': 'cs_9', 'mode': 'payment', 'payment_status': 'paid',
                                                                      'client_reference_id': uid, 'metadata': {'user_id': uid, 'minutes': '60'}}}}
    unpaid = {'type': 'checkout.session.completed', 'data': {'object': {**paid['data']['object'], 'id': 'cs_10', 'payment_status': 'unpaid'}}}
    assert send(client, unpaid).status_code == 200
    assert client.get(f'{API}/me').json()['ai_credit_seconds'] == 300  # SEPA not paid yet: nothing booked
    assert send(client, paid).status_code == 200 and send(client, paid).status_code == 200  # Stripe repeats events
    assert client.get(f'{API}/me').json()['ai_credit_seconds'] == 300 + 3600


def test_forged_or_old_webhooks_are_refused(client, stripe):
    uid = signup(client)['user']['id']
    event = {'type': 'checkout.session.completed', 'data': {'object': {'id': 'cs_x', 'mode': 'payment', 'payment_status': 'paid',
                                                                       'metadata': {'user_id': uid, 'minutes': '300'}}}}
    assert send(client, event, secret='whsec_wrong').status_code == 400
    assert send(client, event, age=3600).status_code == 400
    assert client.post(f'{API}/billing/webhook', content=b'{}').status_code == 400
    assert client.get(f'{API}/me').json()['ai_credit_seconds'] == 300


def test_flatten_matches_stripe_form_encoding():
    assert billing.flatten({'mode': 'payment', 'line_items': [{'price': 'p', 'quantity': 1}], 'metadata': {'a': 'b'}, 'x': None, 'y': True}) == {
        'mode': 'payment', 'line_items[0][price]': 'p', 'line_items[0][quantity]': '1', 'metadata[a]': 'b', 'y': 'true'}
