"""Churches and ministries as customers ("organisations").

The platform admin creates an organisation (name, address, logo, colour, apps, plan) and
names its admin. The organisation gets its own page at /<slug>; its admins invite people
by email or share a join link. While the organisation's plan runs, every member has Pro.
Imported at the end of main.py, so the helpers defined there are available.
"""
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

import db
import main as m

router = APIRouter()

APPS = ('eventpass', 'sermon-ai', 'bodyofchrist', 'projection')
# Addresses that belong to the platform itself and can never be a church page.
RESERVED = {'api', 'admin', 'account', 'apps', 'about', 'contact', 'pricing', 'login', 'register', 'logout',
            'forgot-password', 'reset-password', 'eventpass', 'sermon-ai', 'bodyofchrist', 'projection',
            'bible-study', 'assets', 'static', 'join', 'org', 'orgs', 'www', 'mail', 'help', 'support', 'cmgi'}
SLUG = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$')
COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def clean_slug(value: str):
    slug = value.strip().lower()
    if not SLUG.match(slug) or len(slug) < 2: raise HTTPException(422, 'Address: 2–40 letters, digits or dashes')
    if slug in RESERVED: raise HTTPException(422, 'This address is reserved')
    return slug


def clean_logo(value: str):
    logo = value.strip()
    if not logo: return ''
    if logo.startswith('https://') and len(logo) <= 1000: return logo
    if re.match(r'^data:image/(png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$', logo) and len(logo) <= 400_000: return logo
    raise HTTPException(422, 'Logo: an https:// link or an image up to 300 KB')


def clean_apps(values: list[str]):
    apps = [a for a in APPS if a in values]
    if not apps: raise HTTPException(422, 'Choose at least one app')
    return ','.join(apps)


def org_has_pro(org, at: datetime):
    return (not org.disabled_at and org.plan == 'pro'
            and (org.pro_until is None or m.aware(org.pro_until) > at))


def memberships(c, user_id):
    rows = c.execute(select(db.organisations, db.org_members.c.role)
                     .join(db.org_members, db.org_members.c.org_id == db.organisations.c.id)
                     .where(db.org_members.c.user_id == user_id).order_by(db.organisations.c.name))
    return [(row, row.role) for row in rows]  # (organisation row, role of this user)


def member_count(c, org_id):
    return int(c.execute(select(func.count()).select_from(db.org_members).where(db.org_members.c.org_id == org_id)).scalar_one())


def add_member(c, org, user_id, role):
    """Adds or upgrades a membership; respects the seat limit for new members."""
    current = c.execute(select(db.org_members).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user_id)).first()
    if current:
        if role == 'admin' and current.role != 'admin':
            c.execute(update(db.org_members).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user_id).values(role='admin'))
        return False
    if org.seats and member_count(c, org.id) >= org.seats:
        raise HTTPException(409, 'All places of this organisation are taken. Please contact its admin.')
    c.execute(insert(db.org_members).values(org_id=org.id, user_id=user_id, role=role, created_at=m.now()))
    return True


def apply_invites(c, user):
    """Pending invitations for this (confirmed) email address become memberships."""
    if not user.email_verified_at: return
    for inv in list(c.execute(select(db.org_invites).where(db.org_invites.c.email == user.email))):
        org = c.execute(select(db.organisations).where(db.organisations.c.id == inv.org_id)).first()
        try:
            with c.begin_nested():
                add_member(c, org, user.id, inv.role)
        except HTTPException:
            continue  # no free place: the invitation stays open
        c.execute(delete(db.org_invites).where(db.org_invites.c.id == inv.id))


def public_org(org):
    return {'slug': org.slug, 'name': org.name, 'logo': org.logo, 'color': org.color, 'welcome': org.welcome,
            'apps': [a for a in org.apps.split(',') if a], 'active': not org.disabled_at}


def admin_org(c, org):
    return {**public_org(org), 'id': org.id, 'plan': org.plan, 'pro_until': m.iso(org.pro_until), 'seats': org.seats,
            'price_note': org.price_note, 'disabled': bool(org.disabled_at), 'created_at': m.iso(org.created_at),
            'members': member_count(c, org.id), 'pro_active': org_has_pro(org, m.now())}


def load_org(c, slug):
    org = c.execute(select(db.organisations).where(db.organisations.c.slug == slug.strip().lower())).first()
    if not org: raise HTTPException(404, 'Organisation not found')
    return org


def org_role(c, org, user):
    row = c.execute(select(db.org_members.c.role).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user.id)).first()
    return row.role if row else None


def require_org_admin(c, org, user):
    if user.email in m.ADMIN_EMAILS: return
    if org_role(c, org, user) != 'admin': raise HTTPException(403, 'Only admins of this organisation can do this')


def invite(c, org, email, role, actor, request, background):
    email = m.clean_email(email)
    if role not in ('admin', 'member'): raise HTTPException(422, 'Unknown role')
    user = c.execute(select(db.users).where(db.users.c.email == email)).first()
    if user and user.email_verified_at:
        add_member(c, org, user.id, role)
        status = 'added'
    else:
        existing = c.execute(select(db.org_invites).where(db.org_invites.c.org_id == org.id, db.org_invites.c.email == email)).first()
        if existing: c.execute(update(db.org_invites).where(db.org_invites.c.id == existing.id).values(role=role))
        else: c.execute(insert(db.org_invites).values(org_id=org.id, email=email, role=role, invited_by=actor, created_at=m.now()))
        status = 'invited'
    link = f'{m.public_base(request)}/{org.slug}'
    if m.mailer.enabled():
        intro = (f'You have been added to {org.name} on CMGI Apps.' if status == 'added' else
                 f'You are invited to {org.name} on CMGI Apps. Create your account with this email address ({email}) to join.')
        background.add_task(m.send_mail, email, f'{org.name} on CMGI Apps', intro, link, f'Open {org.name}')
    m.audit(c, actor, f'org_{status}', user.id if user else None, f'{org.slug} {email} {role}')
    return {'status': status, 'email': email, 'role': role, 'link': link, 'mail': m.mailer.enabled()}


# ---- platform admin ----
class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(max_length=40)
    logo: str = Field(default='', max_length=400_000)
    color: str = Field(default='#1764d8', max_length=7)
    welcome: str = Field(default='', max_length=2000)
    apps: list[str] = Field(default_factory=lambda: ['eventpass', 'sermon-ai', 'bodyofchrist'])
    plan: str = Field(default='pro', max_length=20)
    pro_until: datetime | None = None
    seats: int = Field(default=0, ge=0, le=100_000)
    price_note: str = Field(default='', max_length=300)
    admin_email: str = Field(default='', max_length=200)


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    logo: str | None = Field(default=None, max_length=400_000)
    color: str | None = Field(default=None, max_length=7)
    welcome: str | None = Field(default=None, max_length=2000)
    apps: list[str] | None = None
    plan: str | None = Field(default=None, max_length=20)
    pro_until: datetime | None = None
    clear_pro_until: bool = False
    seats: int | None = Field(default=None, ge=0, le=100_000)
    price_note: str | None = Field(default=None, max_length=300)
    disabled: bool | None = None


def check_common(data):
    values = {}
    if getattr(data, 'logo', None) is not None: values['logo'] = clean_logo(data.logo)
    if getattr(data, 'color', None) is not None:
        if not COLOR.match(data.color): raise HTTPException(422, 'Colour: a value like #1764d8')
        values['color'] = data.color.lower()
    if getattr(data, 'welcome', None) is not None: values['welcome'] = data.welcome.strip()
    if getattr(data, 'name', None) is not None: values['name'] = data.name.strip()
    return values


@router.get('/admin/orgs')
def list_orgs(authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        m.require_admin(c, authorization, cmgi_session)
        return [admin_org(c, o) for o in c.execute(select(db.organisations).order_by(db.organisations.c.name))]


@router.post('/admin/orgs', status_code=201)
def create_org(data: OrgIn, request: Request, background: BackgroundTasks, authorization: str | None = Header(default=None),
               cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    if data.plan not in ('pro', 'free'): raise HTTPException(422, 'Unknown plan')
    if data.pro_until and m.aware(data.pro_until) <= m.now(): raise HTTPException(422, 'The end date must be in the future')
    values = check_common(data)
    with db.engine.begin() as c:
        admin = m.require_admin(c, authorization, cmgi_session)
        oid = m.ident()
        try:
            with c.begin_nested():
                c.execute(insert(db.organisations).values(
                    id=oid, slug=clean_slug(data.slug), apps=clean_apps(data.apps), plan=data.plan,
                    pro_until=data.pro_until, seats=data.seats, price_note=data.price_note.strip(),
                    join_code=secrets.token_urlsafe(9), created_at=m.now(), **values))
        except IntegrityError:
            raise HTTPException(409, 'This address is already taken')
        org = c.execute(select(db.organisations).where(db.organisations.c.id == oid)).first()
        m.audit(c, admin.email, 'org_create', None, org.slug)
        result = admin_org(c, org)
        if data.admin_email.strip():
            result['invite'] = invite(c, org, data.admin_email, 'admin', admin.email, request, background)
        return result


@router.patch('/admin/orgs/{slug}')
def update_org(slug: str, data: OrgPatch, request: Request, authorization: str | None = Header(default=None),
               cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    values = check_common(data)
    if data.apps is not None: values['apps'] = clean_apps(data.apps)
    if data.plan is not None:
        if data.plan not in ('pro', 'free'): raise HTTPException(422, 'Unknown plan')
        values['plan'] = data.plan
    if data.pro_until is not None: values['pro_until'] = data.pro_until
    if data.clear_pro_until: values['pro_until'] = None
    if data.seats is not None: values['seats'] = data.seats
    if data.price_note is not None: values['price_note'] = data.price_note.strip()
    if data.disabled is not None: values['disabled_at'] = m.now() if data.disabled else None
    with db.engine.begin() as c:
        admin = m.require_admin(c, authorization, cmgi_session)
        org = load_org(c, slug)
        if values: c.execute(update(db.organisations).where(db.organisations.c.id == org.id).values(**values))
        m.audit(c, admin.email, 'org_update', None, f'{org.slug} {sorted(values)}')
        return admin_org(c, load_org(c, slug))


# ---- organisation page and its admins ----
@router.get('/orgs/{slug}/public')
def org_public(slug: str):
    with db.engine.connect() as c:
        org = load_org(c, slug)
        if org.disabled_at: raise HTTPException(404, 'Organisation not found')
        return public_org(org)


@router.get('/orgs/{slug}')
def org_detail(slug: str, authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    with db.engine.connect() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        role = org_role(c, org, user)
        platform_admin = user.email in m.ADMIN_EMAILS
        out = {**public_org(org), 'role': role, 'pro_active': org_has_pro(org, m.now()), 'can_manage': role == 'admin' or platform_admin}
        if out['can_manage']:
            rows = c.execute(select(db.users.c.id, db.users.c.name, db.users.c.email, db.org_members.c.role, db.org_members.c.created_at)
                             .join(db.org_members, db.org_members.c.user_id == db.users.c.id)
                             .where(db.org_members.c.org_id == org.id).order_by(db.users.c.name))
            out['members'] = [{'id': r.id, 'name': r.name, 'email': r.email, 'role': r.role, 'joined': m.iso(r.created_at)} for r in rows]
            out['invites'] = [{'email': i.email, 'role': i.role, 'created_at': m.iso(i.created_at)}
                              for i in c.execute(select(db.org_invites).where(db.org_invites.c.org_id == org.id).order_by(db.org_invites.c.email))]
            out['join_code'] = org.join_code
            out['seats'] = org.seats
            out['pro_until'] = m.iso(org.pro_until)
        return out


class JoinIn(BaseModel):
    code: str = Field(max_length=60)


@router.post('/orgs/{slug}/join')
def org_join(slug: str, data: JoinIn, request: Request, authorization: str | None = Header(default=None),
             cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        if org.disabled_at or not secrets.compare_digest(data.code.strip(), org.join_code):
            raise HTTPException(403, 'This join link is not valid (anymore)')
        add_member(c, org, user.id, 'member')
        return {'ok': True, 'role': org_role(c, org, user)}


class InviteIn(BaseModel):
    email: str = Field(max_length=200)
    role: str = Field(default='member', max_length=20)


@router.post('/orgs/{slug}/invites')
def org_invite(slug: str, data: InviteIn, request: Request, background: BackgroundTasks,
               authorization: str | None = Header(default=None), cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        require_org_admin(c, org, user)
        return invite(c, org, data.email, data.role, user.email, request, background)


@router.delete('/orgs/{slug}/invites')
def org_cancel_invite(slug: str, email: str, request: Request, authorization: str | None = Header(default=None),
                      cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        require_org_admin(c, org, user)
        c.execute(delete(db.org_invites).where(db.org_invites.c.org_id == org.id, db.org_invites.c.email == email.strip().lower()))
        return {'ok': True}


class RoleIn(BaseModel):
    role: str = Field(max_length=20)


def other_admin_left(c, org, user_id):
    return c.execute(select(func.count()).select_from(db.org_members).where(
        db.org_members.c.org_id == org.id, db.org_members.c.role == 'admin', db.org_members.c.user_id != user_id)).scalar_one() > 0


@router.patch('/orgs/{slug}/members/{user_id}')
def org_set_role(slug: str, user_id: str, data: RoleIn, request: Request, authorization: str | None = Header(default=None),
                 cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    if data.role not in ('admin', 'member'): raise HTTPException(422, 'Unknown role')
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        require_org_admin(c, org, user)
        if data.role == 'member' and not other_admin_left(c, org, user_id):
            raise HTTPException(409, 'An organisation needs at least one admin')
        c.execute(update(db.org_members).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user_id).values(role=data.role))
        return {'ok': True}


@router.delete('/orgs/{slug}/members/{user_id}')
def org_remove_member(slug: str, user_id: str, request: Request, authorization: str | None = Header(default=None),
                      cmgi_session: str | None = Cookie(default=None)):
    m.same_origin(request)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        if user.id != user_id: require_org_admin(c, org, user)  # everyone may leave on their own
        target = c.execute(select(db.org_members.c.role).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user_id)).first()
        if target and target.role == 'admin' and not other_admin_left(c, org, user_id):
            raise HTTPException(409, 'An organisation needs at least one admin')
        c.execute(delete(db.org_members).where(db.org_members.c.org_id == org.id, db.org_members.c.user_id == user_id))
        return {'ok': True}


class BrandIn(BaseModel):
    logo: str | None = Field(default=None, max_length=400_000)
    color: str | None = Field(default=None, max_length=7)
    welcome: str | None = Field(default=None, max_length=2000)


@router.patch('/orgs/{slug}')
def org_brand(slug: str, data: BrandIn, request: Request, authorization: str | None = Header(default=None),
              cmgi_session: str | None = Cookie(default=None)):
    """The organisation's own admins may change their page (logo, colour, welcome text) — not the plan."""
    m.same_origin(request)
    values = check_common(data)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        require_org_admin(c, org, user)
        if values: c.execute(update(db.organisations).where(db.organisations.c.id == org.id).values(**values))
        return public_org(load_org(c, slug))


@router.post('/orgs/{slug}/join-code')
def org_new_join_code(slug: str, request: Request, authorization: str | None = Header(default=None),
                      cmgi_session: str | None = Cookie(default=None)):
    """A new join link; the old one stops working."""
    m.same_origin(request)
    with db.engine.begin() as c:
        user = m.current_user(c, authorization, cmgi_session)
        org = load_org(c, slug)
        require_org_admin(c, org, user)
        code = secrets.token_urlsafe(9)
        c.execute(update(db.organisations).where(db.organisations.c.id == org.id).values(join_code=code))
        return {'join_code': code}
