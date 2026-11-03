"""Payments with Stripe: the Pro subscription (one for all CMGI apps) and AI-minute packages.

Uses Stripe's REST API directly (form-encoded requests) so there is no SDK version to keep
up with. Nothing is unlocked by the browser: access changes only when Stripe's signed
webhook confirms a payment.

Configuration (all optional; without STRIPE_SECRET_KEY online payment is simply off):
  STRIPE_SECRET_KEY        sk_live_... / sk_test_...
  STRIPE_WEBHOOK_SECRET    whsec_... (Developers -> Webhooks -> endpoint .../api/accounts/billing/webhook)
  STRIPE_PRO_PRICE         price_... of the recurring Pro price
  STRIPE_PRO_LABEL         shown on the plans page, e.g. "4.99 € / month"
  STRIPE_MINUTE_PACKS      "60|price_abc|9 €,300|price_def|39 €"  (minutes|price id|label)
"""
import hashlib, hmac, os, time

import httpx
from fastapi import HTTPException

API = 'https://api.stripe.com/v1'
SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '').strip()
WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '').strip()
PRO_PRICE = os.getenv('STRIPE_PRO_PRICE', '').strip()
PRO_LABEL = os.getenv('STRIPE_PRO_LABEL', '').strip()
WEBHOOK_TOLERANCE = 300  # seconds, as recommended by Stripe


def parse_packs(raw: str):
    packs = []
    for item in filter(None, (x.strip() for x in raw.split(','))):
        parts = item.split('|')
        if len(parts) >= 2 and parts[0].strip().isdigit():
            packs.append({'minutes': int(parts[0]), 'price': parts[1].strip(), 'label': parts[2].strip() if len(parts) > 2 else ''})
    return packs


PACKS = parse_packs(os.getenv('STRIPE_MINUTE_PACKS', ''))


def enabled():
    return bool(SECRET_KEY and WEBHOOK_SECRET)


def public_config():
    return {'enabled': enabled(), 'pro': bool(enabled() and PRO_PRICE), 'pro_label': PRO_LABEL,
            'packs': [{'minutes': p['minutes'], 'label': p['label']} for p in PACKS] if enabled() else []}


def flatten(data, prefix=''):
    """Stripe expects nested parameters as metadata[user_id]=..., line_items[0][price]=..."""
    out = {}
    for key, value in data.items():
        name = f'{prefix}[{key}]' if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, name))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                out.update(flatten(item, f'{name}[{i}]') if isinstance(item, dict) else {f'{name}[{i}]': item})
        elif value is not None:
            out[name] = str(value).lower() if isinstance(value, bool) else str(value)
    return out


def call(method: str, path: str, data: dict | None = None):
    if not SECRET_KEY: raise HTTPException(503, 'Online payment is not set up yet.')
    try:
        r = httpx.request(method, f'{API}{path}', data=flatten(data or {}), auth=(SECRET_KEY, ''), timeout=20)
    except httpx.HTTPError:
        raise HTTPException(503, 'The payment provider is not reachable right now. Please try again shortly.')
    if r.status_code >= 400:
        message = (r.json().get('error') or {}).get('message', '') if r.headers.get('content-type', '').startswith('application/json') else ''
        print(f'stripe: {method} {path} -> {r.status_code} {message}')
        raise HTTPException(502, 'The payment could not be started. Please try again or contact CMGI.')
    return r.json()


def verify_webhook(payload: bytes, header: str | None):
    """Checks Stripe's signature header ("t=...,v1=...") so nobody can fake a payment."""
    if not WEBHOOK_SECRET or not header: raise HTTPException(400, 'Missing signature')
    parts = {}
    for item in header.split(','):
        key, _, value = item.partition('=')
        parts.setdefault(key.strip(), []).append(value.strip())
    try:
        timestamp = int(parts.get('t', ['0'])[0])
    except ValueError:
        raise HTTPException(400, 'Bad signature')
    if abs(time.time() - timestamp) > WEBHOOK_TOLERANCE: raise HTTPException(400, 'Signature too old')
    expected = hmac.new(WEBHOOK_SECRET.encode(), f'{timestamp}.'.encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in parts.get('v1', [])):
        raise HTTPException(400, 'Bad signature')


def period_end(subscription: dict):
    """current_period_end moved from the subscription to its items in newer Stripe API versions."""
    if subscription.get('current_period_end'): return subscription['current_period_end']
    items = (subscription.get('items') or {}).get('data') or []
    return items[0].get('current_period_end') if items else None
