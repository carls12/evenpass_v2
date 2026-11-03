"""CMGI Accounts — one login for all CMGI apps, Pro access and AI credits.

Web: the session is an httpOnly cookie for the whole domain, so every app under it
(/eventpass, /sermon-ai, /bodyofchrist) sees the same login. Mobile app: the same
token as "Authorization: Bearer". App backends ask GET /api/accounts/me with the
user's cookie/header to learn who is signed in and what they may use.
"""
import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timedelta, timezone
from html import escape

import httpx
from fastapi import APIRouter, BackgroundTasks, Cookie, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

import billing
import db
import google
import mailer

ENV = os.getenv('ACCOUNTS_ENV', 'development')
PUBLIC_URL = os.getenv('ACCOUNTS_PUBLIC_URL', '').strip().rstrip('/')  # e.g. https://cmgi-apps.de (links in emails)
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv('CMGI_ADMIN_EMAILS', '').split(',') if e.strip()}
INTERNAL_KEY = os.getenv('ACCOUNTS_INTERNAL_KEY', '')  # shared with app backends for credit bookings
if ENV == 'production' and len(INTERNAL_KEY) < 24:
    raise RuntimeError('ACCOUNTS_INTERNAL_KEY must be set (min. 24 characters) in production')
SECURE_COOKIE = os.getenv('ACCOUNTS_SECURE_COOKIE', 'false').lower() == 'true'
COOKIE = 'cmgi_session'
SESSION_DAYS = 30
TRIAL_DAYS = int(os.getenv('CMGI_TRIAL_DAYS', '14'))
TRIAL_CREDIT_SECONDS = int(os.getenv('CMGI_TRIAL_CREDIT_SECONDS', '300'))  # 5 minutes of transcription

docs = ENV != 'production'
app = FastAPI(title='CMGI Accounts API', version='1.0', docs_url='/api/accounts/docs' if docs else None,
              redoc_url=None, openapi_url='/api/accounts/openapi.json' if docs else None)
router = APIRouter()
db.init()


def now(): return datetime.now(timezone.utc)
def ident(): return secrets.token_urlsafe(16)
def digest(token: str): return hashlib.sha256(token.encode()).hexdigest()


def aware(dt):
    """SQLite returns naive datetimes; everything is stored in UTC."""
    if dt is None: return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt): return aware(dt).isoformat() if dt else None


# ---- passwords (scrypt, standard library) ----
def hash_password(password: str):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f'scrypt$16384$8$1${salt.hex()}${key.hex()}'


def check_password(password: str, stored: str):
    try:
        _, n, r, p, salt, key = stored.split('$')
        test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(test.hex(), key)
    except ValueError:
        return False


# ---- login throttle (per IP and per email; single worker) ----
LOGIN_LIMIT = int(os.getenv('ACCOUNTS_LOGIN_LIMIT', '10'))
LOGIN_WINDOW = 15 * 60
failures: dict[str, list[float]] = {}


def throttle(*keys: str):
    t = time.monotonic()
    for key in keys:
        recent = [x for x in failures.get(key, []) if t - x < LOGIN_WINDOW]
        failures[key] = recent
        if len(recent) >= LOGIN_LIMIT:
            raise HTTPException(429, 'Too many attempts. Please wait 15 minutes.')


def record_failure(*keys: str):
    if len(failures) > 10000: failures.clear()
    for key in keys: failures.setdefault(key, []).append(time.monotonic())


def client_ip(request: Request):
    return request.client.host if request.client else 'unknown'


# ---- entitlements: what a user may use ----
def credit_balance(c, user_id):
    return int(c.execute(select(func.coalesce(func.sum(db.credit_ledger.c.seconds), 0))
                         .where(db.credit_ledger.c.user_id == user_id)).scalar_one())


def entitlements(c, user):
    t = now()
    sources = []  # (source, until) — until None means no end date
    if user.trial_ends_at and aware(user.trial_ends_at) > t:
        sources.append(('trial', aware(user.trial_ends_at)))
    sub = c.execute(select(db.subscriptions).where(db.subscriptions.c.user_id == user.id)).first()
    if sub and sub.status in ('active', 'trialing') and (not sub.current_period_end or aware(sub.current_period_end) > t):
        sources.append(('subscription', aware(sub.current_period_end)))
    for g in c.execute(select(db.pro_grants).where(db.pro_grants.c.user_id == user.id, db.pro_grants.c.revoked_at.is_(None))):
        if g.until is None or aware(g.until) > t:
            sources.append(('grant', aware(g.until)))
    for org, _role in orgs.memberships(c, user.id):  # Pro paid by the user's church / ministry
        if orgs.org_has_pro(org, t):
            sources.append(('organisation', aware(org.pro_until) if org.pro_until else None))
    # Strongest source first: no end date > subscription > organisation > grant/trial with the latest end.
    order = {'subscription': 1, 'organisation': 2, 'grant': 3, 'trial': 4}
    sources.sort(key=lambda s: (s[1] is not None, order[s[0]], -(s[1].timestamp() if s[1] else 0)))
    best = sources[0] if sources else None
    return {
        'pro': bool(best),
        'pro_source': best[0] if best else None,
        'pro_until': iso(best[1]) if best else None,
        'trial_ends_at': iso(user.trial_ends_at),
        'trial_used': user.trial_ends_at is not None,
        'subscription': {'status': sub.status, 'current_period_end': iso(sub.current_period_end)} if sub else None,
        'ai_credit_seconds': credit_balance(c, user.id),
    }


def public_user(c, user):
    return {'id': user.id, 'email': user.email, 'name': user.name,
            'email_verified': user.email_verified_at is not None,
            'has_password': not user.password_hash.startswith('!'),
            'is_admin': user.email in ADMIN_EMAILS, 'created_at': iso(user.created_at),
            'organisations': [{'slug': o.slug, 'name': o.name, 'role': role, 'color': o.color}
                              for o, role in orgs.memberships(c, user.id) if not o.disabled_at],
            **entitlements(c, user)}


# ---- sessions ----
def session_token(authorization: str | None, cookie: str | None):
    if authorization and authorization.startswith('Bearer '): return authorization[7:].strip()
    return cookie or None


def current_user(c, authorization: str | None, cookie: str | None, required=True):
    token = session_token(authorization, cookie)
    row = None
    if token:
        row = c.execute(select(db.users).join(db.sessions, db.sessions.c.user_id == db.users.c.id)
                        .where(db.sessions.c.token_hash == digest(token), db.sessions.c.expires_at > now())).first()
    if row and row.disabled_at: row = None
    if not row and required: raise HTTPException(401, 'Please sign in')
    return row


def require_admin(c, authorization, cookie):
    user = current_user(c, authorization, cookie)
    if user.email not in ADMIN_EMAILS: raise HTTPException(403, 'Admins only')
    return user


def same_origin(request: Request):
    """Cookie-authenticated changes must come from our own pages (CSRF protection)."""
    origin = request.headers.get('origin')
    if not origin: return
    host = request.headers.get('x-forwarded-host') or request.headers.get('host', '')
    if origin.split('://', 1)[-1] != host:
        raise HTTPException(403, 'Request from another website refused')


def start_session(c, response: Response, user_id: str, client: str):
    token = secrets.token_urlsafe(32)
    c.execute(insert(db.sessions).values(token_hash=digest(token), user_id=user_id, created_at=now(),
                                         expires_at=now() + timedelta(days=SESSION_DAYS), client=client[:200]))
    c.execute(update(db.users).where(db.users.c.id == user_id).values(last_login_at=now()))
    orgs.apply_invites(c, c.execute(select(db.users).where(db.users.c.id == user_id)).first())
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE,
                        samesite='lax', path='/')
    return token


# ---- emails ----
def public_base(request: Request):
    if PUBLIC_URL: return PUBLIC_URL
    proto = request.headers.get('x-forwarded-proto', request.url.scheme).split(',')[0].strip()
    host = request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc
    return f'{proto}://{host}'


def one_time_link(c, user_id, purpose, hours):
    token = secrets.token_urlsafe(32)
    c.execute(insert(db.tokens).values(token_hash=digest(token), user_id=user_id, purpose=purpose,
                                       expires_at=now() + timedelta(hours=hours)))
    return token


def send_mail(to, subject, intro, link, button):
    text = f'{intro}\n\n{link}\n\nCMGI Apps'
    html = f'''<div style="font-family:Arial,sans-serif;color:#173253;max-width:520px">
<h2 style="color:#1764d8">CMGI Apps</h2><p>{escape(intro)}</p>
<p><a href="{escape(link)}" style="background:#1764d8;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:bold">{escape(button)}</a></p>
<p style="color:#5b6f8c;font-size:13px">If the button does not work, copy this link into your browser:<br>{escape(link)}</p></div>'''
    try: mailer.deliver(mailer.build(to, subject, text, html))
    except Exception as exc: print(f'accounts: mail to {to} failed: {type(exc).__name__}: {exc}')


def start_trial(c, user):
    """Called once, when the email address is confirmed: 14 days Pro + 5 minutes of transcription."""
    if user.trial_ends_at is not None: return
    c.execute(update(db.users).where(db.users.c.id == user.id).values(trial_ends_at=now() + timedelta(days=TRIAL_DAYS)))
    c.execute(insert(db.credit_ledger).values(user_id=user.id, seconds=TRIAL_CREDIT_SECONDS, reason='trial',
                                              ref=f'trial:{user.id}', note='Free trial', created_by='system', created_at=now()))


def audit(c, actor, action, user_id=None, detail=''):
    c.execute(insert(db.audit_log).values(actor=actor, action=action, user_id=user_id, detail=detail[:2000], created_at=now()))


# ---- public endpoints ----
class Register(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=2, max_length=120)


class Login(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class Email(BaseModel):
    email: str = Field(max_length=200)


class Reset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)


class Profile(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


def clean_email(value: str):
    email = value.strip().lower()
    if '@' not in email or ' ' in email or email.startswith('@') or email.endswith('@') or '.' not in email.split('@')[-1]:
        raise HTTPException(422, 'Please enter a valid email address')
    return email


@router.get('/health')
def health():
    with db.engine.connect() as c: c.execute(select(1))
    return {'ok': True, 'mail': mailer.enabled()}


@router.post('/register', status_code=201)
def register(data: Register, request: Request, response: Response, background: BackgroundTasks):
    same_origin(request)
    email = clean_email(data.email)
    throttle(f'register:{client_ip(request)}')
    record_failure(f'register:{client_ip(request)}')  # counts every registration: max. LOGIN_LIMIT per 15 min and IP
    uid = ident()
    with db.engine.begin() as c:
        try:
            c.execute(insert(db.users).values(id=uid, email=email, name=data.name.strip(),
                                              password_hash=hash_password(data.password), created_at=now()))
        except IntegrityError:
            raise HTTPException(409, 'An account with this email already exists. Please sign in.')
        user = c.execute(select(db.users).where(db.users.c.id == uid)).first()
        if mailer.enabled():
            token = one_time_link(c, uid, 'verify', 72)
            link = f'{public_base(request)}/api/accounts/verify?token={token}'
            background.add_task(send_mail, email, 'Confirm your CMGI Apps account',
                                f'Hello {data.name.strip()}, please confirm your email address to start your free 14-day Pro trial.',
                                link, 'Confirm email')
        else:
            # Without email sending there is nothing to confirm with: the account is confirmed right away.
            c.execute(update(db.users).where(db.users.c.id == uid).values(email_verified_at=now()))
            start_trial(c, user)
            user = c.execute(select(db.users).where(db.users.c.id == uid)).first()
        token = start_session(c, response, uid, request.headers.get('user-agent', ''))
        return {'token': token, 'user': public_user(c, user), 'verification_sent': mailer.enabled()}


@router.get('/verify')
def verify(token: str = Query(max_length=200)):
    with db.engine.begin() as c:
        row = c.execute(select(db.tokens).where(db.tokens.c.token_hash == digest(token), db.tokens.c.purpose == 'verify')).first()
        if not row or row.used_at or aware(row.expires_at) < now():
            return RedirectResponse('/account?verify=invalid', 303)
        c.execute(update(db.tokens).where(db.tokens.c.token_hash == row.token_hash).values(used_at=now()))
        user = c.execute(select(db.users).where(db.users.c.id == row.user_id)).first()
        if not user.email_verified_at:
            c.execute(update(db.users).where(db.users.c.id == user.id).values(email_verified_at=now()))
        start_trial(c, user)
        orgs.apply_invites(c, c.execute(select(db.users).where(db.users.c.id == user.id)).first())
    return RedirectResponse('/account?verify=ok', 303)


@router.post('/resend-verification')
def resend_verification(request: Request, background: BackgroundTasks, authorization: str | None = Header(default=None),
                        cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    with db.engine.begin() as c:
        user = current_user(c, authorization, cmgi_session)
        if user.email_verified_at or not mailer.enabled(): return {'sent': False}
        throttle(f'verify:{user.id}'); record_failure(f'verify:{user.id}')
        token = one_time_link(c, user.id, 'verify', 72)
    background.add_task(send_mail, user.email, 'Confirm your CMGI Apps account',
                        f'Hello {user.name}, please confirm your email address to start your free 14-day Pro trial.',
                        f'{public_base(request)}/api/accounts/verify?token={token}', 'Confirm email')
    return {'sent': True}


@router.post('/login')
def login(data: Login, request: Request, response: Response):
    same_origin(request)
    email = data.email.strip().lower()
    keys = (f'login:{client_ip(request)}', f'login:{email}')
    throttle(*keys)
    with db.engine.begin() as c:
        user = c.execute(select(db.users).where(db.users.c.email == email)).first()
        if not user or not check_password(data.password, user.password_hash):
            record_failure(*keys); raise HTTPException(401, 'Email or password is incorrect')
        if user.disabled_at: raise HTTPException(403, 'This account has been deactivated. Please contact CMGI.')
        token = start_session(c, response, user.id, request.headers.get('user-agent', ''))
        return {'token': token, 'user': public_user(c, user)}


@router.post('/logout')
def logout(request: Request, response: Response, authorization: str | None = Header(default=None),
           cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    token = session_token(authorization, cmgi_session)
    if token:
        with db.engine.begin() as c: c.execute(db.sessions.delete().where(db.sessions.c.token_hash == digest(token)))
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True}


@router.get('/me')
def me(authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        return public_user(c, current_user(c, authorization, cmgi_session))


@router.patch('/me')
def update_profile(data: Profile, request: Request, authorization: str | None = Header(default=None),
                   cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    with db.engine.begin() as c:
        user = current_user(c, authorization, cmgi_session)
        c.execute(update(db.users).where(db.users.c.id == user.id).values(name=data.name.strip()))
        return public_user(c, c.execute(select(db.users).where(db.users.c.id == user.id)).first())


@router.post('/me/password')
def change_password(data: PasswordChange, request: Request, authorization: str | None = Header(default=None),
                    cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    with db.engine.begin() as c:
        user = current_user(c, authorization, cmgi_session)
        if not check_password(data.current_password, user.password_hash): raise HTTPException(403, 'Current password is incorrect')
        c.execute(update(db.users).where(db.users.c.id == user.id).values(password_hash=hash_password(data.new_password)))
        # Sign out everywhere else.
        keep = digest(session_token(authorization, cmgi_session))
        c.execute(db.sessions.delete().where(db.sessions.c.user_id == user.id, db.sessions.c.token_hash != keep))
    return {'ok': True}


@router.post('/password/forgot')
def forgot_password(data: Email, request: Request, background: BackgroundTasks):
    same_origin(request)
    throttle(f'forgot:{client_ip(request)}'); record_failure(f'forgot:{client_ip(request)}')
    email = data.email.strip().lower()
    with db.engine.begin() as c:
        user = c.execute(select(db.users).where(db.users.c.email == email)).first()
        if user and not user.disabled_at and mailer.enabled():
            token = one_time_link(c, user.id, 'reset', 2)
            background.add_task(send_mail, email, 'Reset your CMGI Apps password',
                                f'Hello {user.name}, use this link within 2 hours to choose a new password.',
                                f'{public_base(request)}/reset-password?token={token}', 'Choose new password')
    # Same answer whether or not the account exists (no account enumeration).
    return {'ok': True, 'mail': mailer.enabled()}


@router.post('/password/reset')
def reset_password(data: Reset, request: Request):
    same_origin(request)
    with db.engine.begin() as c:
        row = c.execute(select(db.tokens).where(db.tokens.c.token_hash == digest(data.token), db.tokens.c.purpose == 'reset')).first()
        if not row or row.used_at or aware(row.expires_at) < now():
            raise HTTPException(400, 'This link is invalid or has expired. Please request a new one.')
        c.execute(update(db.tokens).where(db.tokens.c.token_hash == row.token_hash).values(used_at=now()))
        c.execute(update(db.users).where(db.users.c.id == row.user_id).values(password_hash=hash_password(data.password)))
        c.execute(db.sessions.delete().where(db.sessions.c.user_id == row.user_id))
    return {'ok': True}


# ---- internal: used by app backends (Sermon AI books transcription time) ----
class CreditBooking(BaseModel):
    user_id: str = Field(max_length=32)
    seconds: int = Field(gt=0, le=36000)
    ref: str = Field(min_length=3, max_length=200)
    note: str = Field(default='', max_length=300)


def require_internal(key: str | None):
    if not INTERNAL_KEY or not key or not hmac.compare_digest(key, INTERNAL_KEY):
        raise HTTPException(403, 'Internal endpoint')


@router.get('/internal/users/by-email')
def internal_user_by_email(email: str = Query(max_length=200), x_internal_key: str | None = Header(default=None)):
    """For apps with their own tokens (Body of Christ mobile API): plan of the account with this email."""
    require_internal(x_internal_key)
    with db.engine.connect() as c:
        user = c.execute(select(db.users).where(db.users.c.email == email.strip().lower())).first()
        if not user: raise HTTPException(404, 'User not found')
        data = public_user(c, user)
        if user.disabled_at: data['pro'] = False
        return data


@router.get('/internal/users/{user_id}')
def internal_user(user_id: str, x_internal_key: str | None = Header(default=None)):
    """For app backends acting without the user present, e.g. EventPass gate staff checking the event owner's Pro."""
    require_internal(x_internal_key)
    with db.engine.connect() as c:
        user = c.execute(select(db.users).where(db.users.c.id == user_id)).first()
        if not user: raise HTTPException(404, 'User not found')
        data = public_user(c, user)
        if user.disabled_at: data['pro'] = False
        return data


@router.post('/internal/credits/consume')
def consume_credits(data: CreditBooking, x_internal_key: str | None = Header(default=None)):
    """Books usage once per ref. Refuses (402) when the balance is too low; nothing is booked then."""
    require_internal(x_internal_key)
    with db.engine.begin() as c:
        if c.execute(select(db.credit_ledger.c.id).where(db.credit_ledger.c.ref == data.ref)).first():
            return {'ok': True, 'duplicate': True, 'ai_credit_seconds': credit_balance(c, data.user_id)}
        balance = credit_balance(c, data.user_id)
        if balance < data.seconds: raise HTTPException(402, 'Not enough transcription credit')
        try:
            with c.begin_nested():
                c.execute(insert(db.credit_ledger).values(user_id=data.user_id, seconds=-data.seconds, reason='usage', ref=data.ref,
                                                          note=data.note, created_by='app', created_at=now()))
        except IntegrityError:  # the same booking arrived twice at the same moment
            return {'ok': True, 'duplicate': True, 'ai_credit_seconds': credit_balance(c, data.user_id)}
        return {'ok': True, 'ai_credit_seconds': balance - data.seconds}


@router.post('/internal/credits/refund')
def refund_credits(data: CreditBooking, x_internal_key: str | None = Header(default=None)):
    require_internal(x_internal_key)
    with db.engine.begin() as c:
        try:
            # Savepoint: in PostgreSQL a failed insert would otherwise abort the whole transaction.
            with c.begin_nested():
                c.execute(insert(db.credit_ledger).values(user_id=data.user_id, seconds=data.seconds, reason='refund', ref=data.ref,
                                                          note=data.note, created_by='app', created_at=now()))
        except IntegrityError:
            pass  # already refunded
        return {'ok': True, 'ai_credit_seconds': credit_balance(c, data.user_id)}


# ---- payments (Stripe): Pro subscription and AI-minute packages ----
class Checkout(BaseModel):
    product: str = Field(pattern='^(pro|minutes)$')
    minutes: int | None = None


def stripe_customer(c, user):
    row = c.execute(select(db.billing_customers).where(db.billing_customers.c.user_id == user.id)).first()
    if row: return row.customer_id
    customer = billing.call('POST', '/customers', {'email': user.email, 'name': user.name, 'metadata': {'user_id': user.id}})
    c.execute(insert(db.billing_customers).values(user_id=user.id, customer_id=customer['id'], created_at=now()))
    return customer['id']


@router.get('/billing/config')
def billing_config():
    return billing.public_config()


@router.post('/billing/checkout')
def billing_checkout(data: Checkout, request: Request, authorization: str | None = Header(default=None),
                     cmgi_session: str | None = Cookie(default=None)):
    """Starts Stripe Checkout; the browser goes to the returned URL. Access changes only via the webhook."""
    same_origin(request)
    if not billing.enabled(): raise HTTPException(503, 'Online payment is not set up yet.')
    base = public_base(request)
    with db.engine.begin() as c:
        user = current_user(c, authorization, cmgi_session)
        if data.product == 'pro':
            if not billing.PRO_PRICE: raise HTTPException(503, 'Pro is not on sale online yet.')
            if entitlements(c, user)['pro_source'] == 'subscription':
                raise HTTPException(409, 'You already have a Pro subscription. Manage it in your account.')
            params = {'mode': 'subscription', 'line_items': [{'price': billing.PRO_PRICE, 'quantity': 1}],
                      'subscription_data': {'metadata': {'user_id': user.id}},
                      'success_url': f'{base}/account?paid=pro', 'cancel_url': f'{base}/pricing'}
        else:
            pack = next((p for p in billing.PACKS if p['minutes'] == data.minutes), None)
            if not pack: raise HTTPException(422, 'Unknown minute package')
            params = {'mode': 'payment', 'line_items': [{'price': pack['price'], 'quantity': 1}],
                      'payment_intent_data': {'metadata': {'user_id': user.id, 'minutes': pack['minutes']}},
                      'success_url': f'{base}/account?paid=minutes', 'cancel_url': f'{base}/pricing'}
        params.update({'customer': stripe_customer(c, user), 'client_reference_id': user.id, 'allow_promotion_codes': True,
                       'metadata': {'user_id': user.id, 'product': data.product, 'minutes': data.minutes or ''}})
        session = billing.call('POST', '/checkout/sessions', params)
    return {'url': session['url']}


@router.post('/billing/portal')
def billing_portal(request: Request, authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    """Stripe's customer page: change payment method, download invoices, cancel."""
    same_origin(request)
    with db.engine.begin() as c:
        user = current_user(c, authorization, cmgi_session)
        row = c.execute(select(db.billing_customers).where(db.billing_customers.c.user_id == user.id)).first()
        if not row: raise HTTPException(404, 'There are no payments for this account yet.')
        session = billing.call('POST', '/billing_portal/sessions', {'customer': row.customer_id, 'return_url': f'{public_base(request)}/account'})
    return {'url': session['url']}


def sync_subscription(c, sub: dict):
    user_id = (sub.get('metadata') or {}).get('user_id')
    if not user_id:
        row = c.execute(select(db.billing_customers).where(db.billing_customers.c.customer_id == sub.get('customer'))).first()
        user_id = row.user_id if row else None
    if not user_id or not c.execute(select(db.users.c.id).where(db.users.c.id == user_id)).first():
        print(f"stripe: subscription {sub.get('id')} without a known CMGI account"); return
    end = billing.period_end(sub)
    values = {'provider': 'stripe', 'customer_id': sub.get('customer'), 'subscription_id': sub.get('id'), 'status': sub.get('status', 'unknown'),
              'current_period_end': datetime.fromtimestamp(end, timezone.utc) if end else None, 'updated_at': now()}
    if c.execute(update(db.subscriptions).where(db.subscriptions.c.user_id == user_id).values(**values)).rowcount == 0:
        c.execute(insert(db.subscriptions).values(user_id=user_id, **values))
    audit(c, 'stripe', 'subscription', user_id, f"{values['status']} until {iso(values['current_period_end'])}")


def book_minutes(c, session: dict):
    meta = session.get('metadata') or {}
    user_id, minutes = meta.get('user_id') or session.get('client_reference_id'), str(meta.get('minutes') or '')
    if not user_id or not minutes.isdigit(): return
    try:
        with c.begin_nested():
            c.execute(insert(db.credit_ledger).values(user_id=user_id, seconds=int(minutes) * 60, reason='purchase', ref=f"stripe:{session['id']}",
                                                      note=f'{minutes} min bought online', created_by='stripe', created_at=now()))
        audit(c, 'stripe', 'minutes', user_id, f'+{minutes} min')
    except IntegrityError:
        pass  # Stripe sends events more than once; booked already


@router.post('/billing/webhook')
async def billing_webhook(request: Request):
    payload = await request.body()
    billing.verify_webhook(payload, request.headers.get('stripe-signature'))
    event = json.loads(payload)
    obj = (event.get('data') or {}).get('object') or {}
    kind = event.get('type', '')
    with db.engine.begin() as c:
        if kind in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
            if obj.get('mode') == 'payment' and obj.get('payment_status') == 'paid':
                book_minutes(c, obj)
            elif obj.get('mode') == 'subscription' and obj.get('subscription'):
                sub = billing.call('GET', f"/subscriptions/{obj['subscription']}")
                sub.setdefault('metadata', {}).setdefault('user_id', (obj.get('metadata') or {}).get('user_id'))
                sync_subscription(c, sub)
        elif kind.startswith('customer.subscription.'):
            sync_subscription(c, obj)
    return {'received': True}


# ---- admin console ----
class Grant(BaseModel):
    until: datetime | None = None  # None = without end date
    note: str = Field(default='', max_length=300)


class Credits(BaseModel):
    minutes: int = Field(ge=-6000, le=6000)
    note: str = Field(default='', max_length=300)


class Disable(BaseModel):
    disabled: bool


def admin_user_row(c, user):
    data = public_user(c, user)
    data['disabled'] = user.disabled_at is not None
    data['last_login_at'] = iso(user.last_login_at)
    return data


def load_user(c, user_id):
    user = c.execute(select(db.users).where(db.users.c.id == user_id)).first()
    if not user: raise HTTPException(404, 'User not found')
    return user


@router.get('/admin/overview')
def admin_overview(authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        require_admin(c, authorization, cmgi_session)
        all_users = c.execute(select(db.users)).all()
        rows = [entitlements(c, u) for u in all_users]
        week = now() - timedelta(days=7)
        return {
            'users': len(all_users),
            'new_7_days': sum(1 for u in all_users if aware(u.created_at) > week),
            'pro': sum(1 for r in rows if r['pro']),
            'pro_trial': sum(1 for r in rows if r['pro_source'] == 'trial'),
            'pro_paid': sum(1 for r in rows if r['pro_source'] == 'subscription'),
            'pro_granted': sum(1 for r in rows if r['pro_source'] == 'grant'),
            'mail_enabled': mailer.enabled(),
        }


@router.get('/admin/users')
def admin_users(q: str = Query(default='', max_length=100), authorization: str | None = Header(default=None),
                cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        require_admin(c, authorization, cmgi_session)
        stmt = select(db.users).order_by(db.users.c.created_at.desc()).limit(200)
        if q.strip():
            like = f'%{q.strip().lower()}%'
            stmt = stmt.where(or_(func.lower(db.users.c.email).like(like), func.lower(db.users.c.name).like(like)))
        return [admin_user_row(c, u) for u in c.execute(stmt)]


@router.get('/admin/users/{user_id}')
def admin_user_detail(user_id: str, authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        grants = c.execute(select(db.pro_grants).where(db.pro_grants.c.user_id == user_id).order_by(db.pro_grants.c.created_at.desc())).all()
        ledger = c.execute(select(db.credit_ledger).where(db.credit_ledger.c.user_id == user_id).order_by(db.credit_ledger.c.id.desc()).limit(50)).all()
        return {**admin_user_row(c, user),
                'grants': [{'id': g.id, 'until': iso(g.until), 'note': g.note, 'granted_by': g.granted_by,
                            'created_at': iso(g.created_at), 'revoked_at': iso(g.revoked_at)} for g in grants],
                'credits': [{'seconds': l.seconds, 'reason': l.reason, 'note': l.note, 'created_by': l.created_by,
                             'created_at': iso(l.created_at)} for l in ledger]}


@router.post('/admin/users/{user_id}/pro')
def admin_grant_pro(user_id: str, data: Grant, request: Request, authorization: str | None = Header(default=None),
                    cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    with db.engine.begin() as c:
        admin = require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        until = data.until.astimezone(timezone.utc) if data.until and data.until.tzinfo else (data.until.replace(tzinfo=timezone.utc) if data.until else None)
        if until and until <= now(): raise HTTPException(422, 'The end date must be in the future')
        c.execute(insert(db.pro_grants).values(user_id=user.id, until=until, note=data.note, granted_by=admin.email, created_at=now()))
        audit(c, admin.email, 'grant_pro', user.id, f'until={iso(until) or "no end"} {data.note}')
        return admin_user_row(c, user)


@router.delete('/admin/users/{user_id}/pro')
def admin_revoke_pro(user_id: str, request: Request, authorization: str | None = Header(default=None),
                     cmgi_session: str | None = Cookie(default=None)):
    """Ends Pro given by an admin. A paid subscription or a running trial is not affected."""
    same_origin(request)
    with db.engine.begin() as c:
        admin = require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        c.execute(update(db.pro_grants).where(and_(db.pro_grants.c.user_id == user.id, db.pro_grants.c.revoked_at.is_(None))).values(revoked_at=now()))
        audit(c, admin.email, 'revoke_pro', user.id)
        return admin_user_row(c, user)


@router.post('/admin/users/{user_id}/credits')
def admin_credits(user_id: str, data: Credits, request: Request, authorization: str | None = Header(default=None),
                  cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    if data.minutes == 0: raise HTTPException(422, 'Enter a number of minutes')
    with db.engine.begin() as c:
        admin = require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        c.execute(insert(db.credit_ledger).values(user_id=user.id, seconds=data.minutes * 60, reason='admin', ref=None,
                                                  note=data.note, created_by=admin.email, created_at=now()))
        audit(c, admin.email, 'credits', user.id, f'{data.minutes:+d} min {data.note}')
        return admin_user_row(c, user)


@router.post('/admin/users/{user_id}/disable')
def admin_disable(user_id: str, data: Disable, request: Request, authorization: str | None = Header(default=None),
                  cmgi_session: str | None = Cookie(default=None)):
    same_origin(request)
    with db.engine.begin() as c:
        admin = require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        if user.id == admin.id: raise HTTPException(422, 'You cannot deactivate your own account')
        c.execute(update(db.users).where(db.users.c.id == user.id).values(disabled_at=now() if data.disabled else None))
        if data.disabled: c.execute(db.sessions.delete().where(db.sessions.c.user_id == user.id))
        audit(c, admin.email, 'disable' if data.disabled else 'enable', user.id)
        return admin_user_row(c, load_user(c, user.id))


@router.post('/admin/users/{user_id}/reset-link')
def admin_reset_link(user_id: str, request: Request, authorization: str | None = Header(default=None),
                     cmgi_session: str | None = Cookie(default=None)):
    """For people who cannot receive email: the admin passes the link on personally."""
    same_origin(request)
    with db.engine.begin() as c:
        admin = require_admin(c, authorization, cmgi_session)
        user = load_user(c, user_id)
        token = one_time_link(c, user.id, 'reset', 24)
        audit(c, admin.email, 'reset_link', user.id)
    return {'link': f'{public_base(request)}/reset-password?token={token}', 'valid_hours': 24}


# ---- sign in with Google ----
OAUTH_COOKIE = 'cmgi_oauth'


def safe_next(value: str | None):
    """Only paths on this site, so the login can never send someone to a foreign page."""
    value = (value or '').strip()
    return value if value.startswith('/') and not value.startswith(('//', '/\\')) else '/account'


@router.get('/providers')
def providers():
    return {'google': google.enabled()}


@router.get('/google/start')
def google_start(request: Request, next: str = Query(default='/account', max_length=500)):
    if not google.enabled(): raise HTTPException(404, 'Google sign-in is not set up')
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(google.authorize_url(f'{public_base(request)}/api/accounts/google/callback', state), 303)
    response.set_cookie(OAUTH_COOKIE, f'{state}|{safe_next(next)}', max_age=600, httponly=True, secure=SECURE_COOKIE,
                        samesite='lax', path='/api/accounts/google')
    return response


@router.get('/google/callback')
def google_callback(request: Request, code: str = Query(default='', max_length=2000), state: str = Query(default='', max_length=200),
                    error: str = Query(default='', max_length=200), cmgi_oauth: str | None = Cookie(default=None)):
    expected, _, target = (cmgi_oauth or '').partition('|')
    def fail(reason):
        r = RedirectResponse(f'/login?error={reason}', 303); r.delete_cookie(OAUTH_COOKIE, path='/api/accounts/google'); return r
    if not google.enabled(): return fail('google')
    if error: return fail('google_cancelled')
    if not code or not expected or not hmac.compare_digest(expected, state): return fail('google')
    try: profile = google.fetch_profile(code, f'{public_base(request)}/api/accounts/google/callback')
    except (ValueError, httpx.HTTPError) as exc:
        print(f'accounts: Google sign-in failed: {exc}'); return fail('google')
    with db.engine.begin() as c:
        link = c.execute(select(db.identities).where(db.identities.c.provider == 'google',
                                                     db.identities.c.subject == profile['sub'])).first()
        user = c.execute(select(db.users).where(db.users.c.id == link.user_id)).first() if link else None
        if not user:
            if not profile['email_verified']: return fail('google_unverified')
            user = c.execute(select(db.users).where(db.users.c.email == profile['email'])).first()
            if not user:  # first visit: new CMGI account, confirmed by Google
                uid = ident()
                name = profile['name'] if len(profile['name']) >= 2 else profile['email'].split('@')[0]
                c.execute(insert(db.users).values(id=uid, email=profile['email'], name=name[:120], password_hash='!google',
                                                  email_verified_at=now(), created_at=now()))
                user = c.execute(select(db.users).where(db.users.c.id == uid)).first()
            elif not user.email_verified_at:
                c.execute(update(db.users).where(db.users.c.id == user.id).values(email_verified_at=now()))
            start_trial(c, user)
            c.execute(insert(db.identities).values(provider='google', subject=profile['sub'], user_id=user.id,
                                                   email=profile['email'], created_at=now()))
        if user.disabled_at: return fail('disabled')
        response = RedirectResponse(safe_next(target), 303)
        start_session(c, response, user.id, request.headers.get('user-agent', ''))
    response.delete_cookie(OAUTH_COOKIE, path='/api/accounts/google')
    return response


@router.get('/dev/outbox')
def dev_outbox():
    """Local testing only: shows the mails that would have been sent, with clickable links."""
    if ENV == 'production' or not mailer.MAIL_OUTBOX or mailer.smtp_enabled(): raise HTTPException(404, 'Not found')
    import email, email.policy, glob, re
    from fastapi.responses import HTMLResponse
    rows = []
    for path in sorted(glob.glob(os.path.join(mailer.MAIL_OUTBOX, '*.eml')), reverse=True)[:50]:
        with open(path, 'rb') as f: msg = email.message_from_binary_file(f, policy=email.policy.default)
        part = msg.get_body(preferencelist=('plain',))
        text = part.get_content() if part else ''
        links = ''.join(f'<p><a href="{escape(u)}">{escape(u)}</a></p>' for u in re.findall(r'https?://\S+', text))
        rows.append(f'<article><b>{escape(msg["Subject"] or "")}</b> &rarr; {escape(msg["To"] or "")}'
                    f'<small> {escape(os.path.basename(path)[:15])}</small>{links}</article>')
    body = ''.join(rows) or '<p>No mails yet.</p>'
    return HTMLResponse('<!doctype html><meta charset=utf-8><title>Local outbox</title><style>body{font-family:Arial;max-width:760px;margin:30px auto;color:#173253}'
                        'article{border:1px solid #d7e1ef;border-radius:10px;padding:12px 16px;margin:10px 0}small{color:#5b6f8c}a{word-break:break-all}</style>'
                        f'<h1>Local outbox</h1><p>Mails are not sent on this computer. Newest first.</p>{body}')


import orgs  # noqa: E402  (uses the helpers above)

app.include_router(router, prefix='/api/accounts')
app.include_router(orgs.router, prefix='/api/accounts')
