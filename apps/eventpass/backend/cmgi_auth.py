"""Central CMGI account for this app: who is signed in, and do they have Pro.

The browser sends the platform's session cookie (cmgi_session) with every request to the
same domain; the mobile app sends the same token as "Authorization: Bearer". This module asks
the accounts service (GET /me) and caches the answer briefly, so a page with many requests
causes one lookup. App backends never see passwords.
"""
import hashlib, os, threading, time

import httpx
from fastapi import HTTPException

ACCOUNTS_URL = os.getenv('ACCOUNTS_URL', 'http://127.0.0.1:8020/api/accounts').rstrip('/')
INTERNAL_KEY = os.getenv('ACCOUNTS_INTERNAL_KEY', '')
CACHE_SECONDS = 30
_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def _cached(key, loader):
    t = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and t - hit[0] < CACHE_SECONDS: return hit[1]
    value = loader()
    with _lock:
        if len(_cache) > 5000: _cache.clear()
        _cache[key] = (t, value)
    return value


def _get(path, headers):
    try:
        r = httpx.get(f'{ACCOUNTS_URL}{path}', headers=headers, timeout=5)
    except httpx.HTTPError:
        raise HTTPException(503, 'The CMGI login service is not reachable right now. Please try again shortly.')
    if r.status_code in (401, 403, 404): return None
    if r.status_code != 200: raise HTTPException(503, 'The CMGI login service answered with an error.')
    return r.json()


def account_for_token(token: str | None):
    """The signed-in CMGI account for a session token, or None."""
    if not token: return None
    key = 'tok:' + hashlib.sha256(token.encode()).hexdigest()
    return _cached(key, lambda: _get('/me', {'Authorization': f'Bearer {token}'}))


def account_by_id(user_id: str):
    """Look up an account without its session (e.g. the owner of an event at the gate)."""
    return _cached('id:' + user_id, lambda: _get(f'/internal/users/{user_id}', {'X-Internal-Key': INTERNAL_KEY}))


def clear_cache():
    with _lock: _cache.clear()
