"""Sign in with Google (OAuth 2.0 / OpenID Connect, authorization-code flow).

Off until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set. In the Google Cloud console
the authorised redirect URI is <public URL>/api/accounts/google/callback.
The user's identity is read from Google's userinfo endpoint over TLS with the access token
we just received for our own client, so no token signature check is needed here.
"""
import os
from urllib.parse import urlencode

import httpx

CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '').strip()
CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def enabled():
    return bool(CLIENT_ID and CLIENT_SECRET)


def authorize_url(redirect_uri: str, state: str):
    return AUTH_URL + '?' + urlencode({'client_id': CLIENT_ID, 'redirect_uri': redirect_uri, 'response_type': 'code',
                                       'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})


def fetch_profile(code: str, redirect_uri: str):
    """Returns {'sub', 'email', 'email_verified', 'name'} or raises ValueError."""
    with httpx.Client(timeout=15) as http:
        token = http.post(TOKEN_URL, data={'code': code, 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
                                           'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'})
        if token.status_code != 200: raise ValueError(f'token exchange failed ({token.status_code})')
        info = http.get(USERINFO_URL, headers={'Authorization': f"Bearer {token.json()['access_token']}"})
        if info.status_code != 200: raise ValueError(f'userinfo failed ({info.status_code})')
        data = info.json()
    if not data.get('sub') or not data.get('email'): raise ValueError('incomplete Google profile')
    return {'sub': str(data['sub']), 'email': str(data['email']).strip().lower(),
            'email_verified': data.get('email_verified') in (True, 'true'), 'name': (data.get('name') or '').strip()}
