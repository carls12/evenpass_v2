import os, sqlite3, secrets, io, json, hashlib, hmac, base64, time, csv
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta, date
from contextlib import contextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, APIRouter, HTTPException, Header, Response, Query, Request, BackgroundTasks
from backup import backup_database
import mailer
from html import escape
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydanticField
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE = Path(__file__).resolve().parent
# Optional fonts: no installation required; DejaVu provides a pleasant default.
FONT_DIR = BASE / 'fonts'
FONT_BOLD = 'Helvetica-Bold'
FONT_REGULAR = 'Helvetica'
for font_name, file_name, fallback in [
    ('EventPassBold', 'Montserrat-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ('EventPassRegular', 'Montserrat-Medium.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
]:
    font_file = FONT_DIR / file_name
    if not font_file.exists() and Path(fallback).exists(): font_file = Path(fallback)
    if font_file.exists():
        pdfmetrics.registerFont(TTFont(font_name, str(font_file)))
        if font_name == 'EventPassBold': FONT_BOLD = font_name
        else: FONT_REGULAR = font_name

def show_date(value):
    try: return datetime.strptime(str(value)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError, TypeError): return str(value or '')

ENV = os.getenv('EVENTPASS_ENV', 'development')
DB = Path(os.getenv('EVENTPASS_DB_PATH', str(BASE / 'eventpass.sqlite3')))
ASSETS_DIR = Path(os.getenv('EVENTPASS_ASSETS_DIR', str(BASE / 'badge_assets')))
BACKUP_DIR = Path(os.getenv('EVENTPASS_BACKUP_DIR', str(DB.parent / 'backups')))
DEV_DEFAULT_PASSWORD = 'change-me-before-sharing'
ADMIN_PASSWORD = os.getenv('EVENTPASS_ADMIN_PASSWORD', '')
if ENV == 'production' and (len(ADMIN_PASSWORD) < 12 or ADMIN_PASSWORD == DEV_DEFAULT_PASSWORD):
    raise RuntimeError('EVENTPASS_ADMIN_PASSWORD must be set (min. 12 characters) in production')
ADMIN_PASSWORD = ADMIN_PASSWORD or DEV_DEFAULT_PASSWORD
PUBLIC_URL = os.getenv('EVENTPASS_PUBLIC_URL', '').strip().rstrip('/')  # e.g. https://cmgi-apps.de, used for links in emails
ORIGINS = [o.strip() for o in os.getenv('EVENTPASS_ORIGIN', 'http://localhost:5173,http://localhost:5174').split(',') if o.strip()]
# Check-in days follow the event's local calendar, not the server clock (Docker runs in UTC).
try: TZ = ZoneInfo(os.getenv('EVENTPASS_TIMEZONE', 'Europe/Berlin'))
except ZoneInfoNotFoundError: TZ = None
def today(): return datetime.now(TZ).date() if TZ else date.today()

docs = ENV != 'production'
app = FastAPI(title='EventPass Studio API', version='2.1', docs_url='/api/eventpass/docs' if docs else None, redoc_url=None, openapi_url='/api/eventpass/openapi.json' if docs else None)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=False, allow_methods=['*'], allow_headers=['*'])
router = APIRouter()

@contextmanager
def database():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

MIGRATIONS = [
    ('badge_width_mm', 'ALTER TABLE events ADD COLUMN badge_width_mm INTEGER NOT NULL DEFAULT 85'),
    ('badge_height_mm', 'ALTER TABLE events ADD COLUMN badge_height_mm INTEGER NOT NULL DEFAULT 130'),
    ('badge_heading', "ALTER TABLE events ADD COLUMN badge_heading TEXT NOT NULL DEFAULT ''"),
    ('badge_subtitle', "ALTER TABLE events ADD COLUMN badge_subtitle TEXT NOT NULL DEFAULT 'WORSHIP  ·  WORD  ·  COMMUNITY  ·  IMPACT'"),
    *[(col, f"ALTER TABLE events ADD COLUMN {col} TEXT NOT NULL DEFAULT ''") for col in ('badge_accent','badge_date_label','badge_location_label','badge_qr_label')],
]

def init():
    with database() as c:
        existing = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        cols = {r[1] for r in c.execute('PRAGMA table_info(events)')}
    pending = [sql for col, sql in MIGRATIONS if col not in cols]
    if existing and pending:
        # Rule: never change the schema of a database holding real data without a backup first.
        backup_database(DB, BACKUP_DIR, ASSETS_DIR, label='pre-migration')
    with database() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,title TEXT NOT NULL,location TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,fields TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY,event_id TEXT NOT NULL REFERENCES events(id),name TEXT NOT NULL,email TEXT NOT NULL,category TEXT NOT NULL,meal TEXT NOT NULL,answers TEXT NOT NULL,qr_secret TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,UNIQUE(event_id,email));
        CREATE TABLE IF NOT EXISTS checkins(id INTEGER PRIMARY KEY AUTOINCREMENT,participant_id TEXT NOT NULL REFERENCES participants(id),event_id TEXT NOT NULL REFERENCES events(id),day TEXT NOT NULL,scanned_at TEXT NOT NULL,UNIQUE(participant_id,day));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gate_users(id TEXT PRIMARY KEY,event_id TEXT NOT NULL REFERENCES events(id),username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,password_salt TEXT NOT NULL,password_hash TEXT NOT NULL,expires_at TEXT NOT NULL,can_add INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gate_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES gate_users(id),expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS badge_emails(participant_id TEXT PRIMARY KEY REFERENCES participants(id),status TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',sent_at TEXT NOT NULL);
        ''')
        cols={r[1] for r in c.execute('PRAGMA table_info(events)')}
        for col, sql in MIGRATIONS:
            if col not in cols: c.execute(sql)
        c.execute('DELETE FROM sessions WHERE expires_at<?',(now(),))
        c.execute('DELETE FROM gate_sessions WHERE expires_at<?',(now(),))

def now(): return datetime.now(timezone.utc).isoformat()
def ident(): return secrets.token_urlsafe(12)
init()

# Login throttle: in-process and per client IP (the API runs as a single worker).
LOGIN_LIMIT = int(os.getenv('EVENTPASS_LOGIN_LIMIT', '10'))
LOGIN_WINDOW = 15 * 60
login_failures: dict[str, list[float]] = {}
def check_throttle(request: Request, scope: str):
    key = f'{scope}:{request.client.host if request.client else "unknown"}'
    t = time.monotonic()
    recent = [x for x in login_failures.get(key, []) if t - x < LOGIN_WINDOW]
    login_failures[key] = recent
    if len(recent) >= LOGIN_LIMIT:
        raise HTTPException(429, 'Zu viele fehlgeschlagene Anmeldeversuche. Bitte in 15 Minuten erneut versuchen.')
    return key
def record_failure(key: str):
    if len(login_failures) > 10000: login_failures.clear()
    login_failures.setdefault(key, []).append(time.monotonic())
def require_admin(authorization: str | None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Admin login required')
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with database() as c:
        row = c.execute('SELECT expires_at FROM sessions WHERE token_hash=?',(token_hash,)).fetchone()
    if not row or datetime.fromisoformat(row['expires_at']) < datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired')

def event_row(row):
    d=dict(row); d['fields']=json.loads(d['fields']); return d

class Login(BaseModel): password: str
# Google-Forms-style custom fields. Events created before field types existed have only label/required and read as 'text'.
FIELD_TYPES=('text','textarea','number','email','phone','date','select','radio','checkbox')
CHOICE_TYPES=('select','radio','checkbox')
class Field(BaseModel):
    label: str = PydanticField(min_length=1,max_length=80)
    required: bool = False
    type: str = 'text'
    options: list[str] = PydanticField(default_factory=list,max_length=30)
    help: str = PydanticField(default='',max_length=200)
def clean_fields(fields: list[Field]):
    out=[]
    for f in fields:
        label=f.label.strip()
        if not label: raise HTTPException(422,'Field label must not be empty')
        if f.type not in FIELD_TYPES: raise HTTPException(422,f'Unknown field type: {f.type}')
        options=[]
        for o in (x.strip()[:80] for x in f.options):
            if o and o not in options: options.append(o)
        if f.type in CHOICE_TYPES and len(options)<1: raise HTTPException(422,f'"{label}" needs at least one option')
        out.append({'label':label,'required':f.required,'type':f.type,'options':options if f.type in CHOICE_TYPES else [],'help':f.help.strip()})
    if len({f['label'].lower() for f in out}) != len(out): raise HTTPException(422,'Field labels must be unique')
    return out
def clean_answers(fields, answers):
    labels={f['label'] for f in fields}
    if any(k not in labels for k in answers): raise HTTPException(422,'Unknown field')
    out={}
    for f in fields:
        label=f['label'];kind=f.get('type','text');value=answers.get(label,'')
        if isinstance(value,list):
            if kind!='checkbox': raise HTTPException(422,f'"{label}": only one answer allowed')
            picked=[v.strip() for v in value if v.strip()]
            if any(v not in f['options'] for v in picked): raise HTTPException(422,f'"{label}": invalid option')
            value=', '.join(o for o in f['options'] if o in picked)
        else:
            value=value.strip()
            if value and kind in ('select','radio','checkbox') and value not in f['options']: raise HTTPException(422,f'"{label}": invalid option')
        if not value:
            if f['required']: raise HTTPException(422,'Please fill all required fields')
            continue
        if len(value)>(2000 if kind=='textarea' else 300): raise HTTPException(422,f'"{label}" is too long')
        if kind=='number':
            try: float(value.replace(',','.'))
            except ValueError: raise HTTPException(422,f'"{label}" must be a number')
        if kind=='email' and ('@' not in value or ' ' in value): raise HTTPException(422,f'"{label}" must be an email address')
        if kind=='date':
            try: date.fromisoformat(value)
            except ValueError: raise HTTPException(422,f'"{label}" must be a date')
        out[label]=value
    return out
class EventIn(BaseModel):
    title: str = PydanticField(min_length=2,max_length=120)
    location: str = PydanticField(min_length=2,max_length=120)
    start_date: date
    end_date: date
    fields: list[Field] = PydanticField(default_factory=list,max_length=30)
    badge_width_mm: int = PydanticField(default=85,ge=45,le=200)
    badge_height_mm: int = PydanticField(default=130,ge=60,le=280)
    badge_heading: str = PydanticField(default="",max_length=120)
    badge_subtitle: str = PydanticField(default="WORSHIP  ·  WORD  ·  COMMUNITY  ·  IMPACT",max_length=140)
    badge_accent: str = PydanticField(default="",max_length=100)
    badge_date_label: str = PydanticField(default="",max_length=90)
    badge_location_label: str = PydanticField(default="",max_length=90)
    badge_qr_label: str = PydanticField(default="SCAN FOR CHECK-IN",max_length=90)
class Registration(BaseModel):
    name: str = PydanticField(min_length=2,max_length=120)
    email: str = PydanticField(min_length=5,max_length=200)
    category: str = 'Participant'
    meal: str = 'Standard'
    answers: dict[str,str | list[str]] = PydanticField(default_factory=dict)
class FieldsIn(BaseModel): fields: list[Field] = PydanticField(max_length=30)
class Scan(BaseModel): qr_value: str; day: date | None = None

@router.get('/health')
def health():
    with database() as c: c.execute('SELECT 1').fetchone()
    return {'ok': True}

@router.post('/login')
def login(data: Login, request: Request):
    key=check_throttle(request,'admin')
    if not hmac.compare_digest(data.password.encode(),ADMIN_PASSWORD.encode()):
        record_failure(key); raise HTTPException(401,'Incorrect password')
    token=secrets.token_urlsafe(36)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
    with database() as c: c.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),expiry))
    return {'token':token}

@router.get('/events')
def events(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c: return [event_row(r) for r in c.execute('SELECT * FROM events ORDER BY created_at DESC')]

@router.post('/events',status_code=201)
def create_event(data: EventIn,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if data.end_date < data.start_date: raise HTTPException(422,'End date before start date')
    fields=clean_fields(data.fields)
    event_id=ident()
    with database() as c:
        c.execute('INSERT INTO events(id,title,location,start_date,end_date,fields,created_at,badge_width_mm,badge_height_mm,badge_heading,badge_subtitle,badge_accent,badge_date_label,badge_location_label,badge_qr_label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(event_id,data.title.strip(),data.location.strip(),str(data.start_date),str(data.end_date),json.dumps(fields),now(),data.badge_width_mm,data.badge_height_mm,data.badge_heading,data.badge_subtitle,data.badge_accent,data.badge_date_label,data.badge_location_label,data.badge_qr_label))
    return {'id':event_id}

# Fields may change after registrations started; answers already stored are kept (also for removed fields).
@router.put('/events/{event_id}/fields')
def update_fields(event_id: str,data: FieldsIn,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    fields=clean_fields(data.fields)
    with database() as c:
        if not c.execute('UPDATE events SET fields=? WHERE id=?',(json.dumps(fields),event_id)).rowcount: raise HTTPException(404,'Event nicht gefunden')
    return {'fields':fields}

@router.get('/public/events/{event_id}')
def public_event(event_id: str):
    with database() as c: row=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
    if not row: raise HTTPException(404,'Event not found')
    return event_row(row)

@router.post('/public/events/{event_id}/register',status_code=201)
def register(event_id: str,data: Registration,request: Request,background: BackgroundTasks):
    if data.category not in ('Participant','Guest','Volunteer'): raise HTTPException(422,'Invalid category')
    if data.meal not in ('Standard','Vegetarian','Vegan','Halal','No meal'): raise HTTPException(422,'Invalid meal')
    with database() as c:
        event=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event: raise HTTPException(404,'Event not found')
        answers=clean_answers(json.loads(event['fields']),data.answers)
        pid=ident(); secret=secrets.token_urlsafe(32)
        try:
            c.execute('INSERT INTO participants VALUES (?,?,?,?,?,?,?,?,?)',(pid,event_id,data.name.strip(),data.email.strip().lower(),data.category,data.meal,json.dumps(answers),secret,now()))
        except sqlite3.IntegrityError: raise HTTPException(409,'This email is already registered for the event')
    return {'participant_id':pid,'badge_secret':secret,'email_sent':queue_badge_email(background,pid,request)}

class ManualParticipant(BaseModel):
    name: str = PydanticField(min_length=2,max_length=120)
    email: str = ''
    category: str = PydanticField(default='Pastor',max_length=50)
    meal: str = 'Standard'

@router.post('/events/{event_id}/participants/manual',status_code=201)
def add_manual_participant(event_id: str, data: ManualParticipant, request: Request, background: BackgroundTasks, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if data.category not in ('Participant','Guest','Volunteer','Pastor','Speaker','VIP','Staff'):
        raise HTTPException(422,'Ungültige Rolle')
    pid=ident(); secret=secrets.token_urlsafe(32)
    # Unique internal address when no email is supplied; then no email is sent.
    email=(data.email or '').strip().lower() or f'manual-{pid}@eventpass.invalid'
    with database() as c:
        if not c.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone():
            raise HTTPException(404,'Event nicht gefunden')
        try:
            c.execute('INSERT INTO participants VALUES (?,?,?,?,?,?,?,?,?)',
                (pid,event_id,data.name.strip(),email,data.category,data.meal,'{}',secret,now()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Diese E-Mail-Adresse ist bereits für das Event eingetragen')
    return {'participant_id':pid,'badge_secret':secret,'email_sent':queue_badge_email(background,pid,request)}

@router.get('/public/badge/{secret}/qr.png')
def badge_qr(secret: str):
    with database() as c: row=c.execute('SELECT id FROM participants WHERE qr_secret=?',(secret,)).fetchone()
    if not row: raise HTTPException(404,'Badge not found')
    img=qrcode.make('EVP:'+secret)
    buf=io.BytesIO(); img.save(buf,format='PNG')
    return Response(buf.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})


# Temporary, event-scoped gate staff credentials. Passwords are salted and never stored in plaintext.
class GateCreate(BaseModel):
    display_name: str = PydanticField(min_length=2,max_length=100)
    username: str = PydanticField(min_length=3,max_length=60)
    expires_at: datetime
    can_add: bool = False

class GateLogin(BaseModel):
    username: str
    password: str

class GateScan(BaseModel):
    qr_value: str
    day: date | None = None

def password_digest(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000).hex()

def gate_user(authorization, event_id=None, allow_add=False):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'Tor-Zugang erforderlich')
    token_hash=hashlib.sha256(authorization[7:].encode()).hexdigest()
    with database() as c:
        row=c.execute('''SELECT u.* FROM gate_sessions s JOIN gate_users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>?''',(token_hash,now())).fetchone()
    if not row or row['revoked'] or row['expires_at'] <= now():
        raise HTTPException(401,'Zugang abgelaufen oder deaktiviert')
    if event_id is not None and row['event_id'] != event_id:
        raise HTTPException(403,'Kein Zugang zu diesem Event')
    if allow_add and not row['can_add']:
        raise HTTPException(403,'Keine Berechtigung, Teilnehmer hinzuzufügen')
    return row

@router.post('/events/{event_id}/gate-users',status_code=201)
def create_gate_user(event_id: str, data: GateCreate, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    expiry=data.expires_at.astimezone(timezone.utc) if data.expires_at.tzinfo else None
    if expiry is None or expiry <= datetime.now(timezone.utc) or expiry > datetime.now(timezone.utc)+timedelta(days=90):
        raise HTTPException(422,'Ablaufdatum muss in der Zukunft und höchstens 90 Tage entfernt liegen (Zeitzone erforderlich)')
    username=data.username.strip().lower()
    if not all(c.isascii() and (c.isalnum() or c in '._-') for c in username):
        raise HTTPException(422,'Benutzername: nur Buchstaben, Zahlen, Punkt, _ und -')
    pwd=secrets.token_urlsafe(18);salt=secrets.token_hex(16)
    with database() as c:
        if not c.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone(): raise HTTPException(404,'Event nicht gefunden')
        try:
            c.execute('INSERT INTO gate_users VALUES (?,?,?,?,?,?,?,?,?,?)',
                (ident(),event_id,username,data.display_name.strip(),salt,password_digest(pwd,salt),expiry.isoformat(),int(data.can_add),0,now()))
        except sqlite3.IntegrityError: raise HTTPException(409,'Benutzername bereits vergeben')
    return {'username':username,'display_name':data.display_name.strip(),'password':pwd,'expires_at':expiry.isoformat(),'can_add':data.can_add}

@router.get('/events/{event_id}/gate-users')
def list_gate_users(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        return [dict(r) for r in c.execute('SELECT id,username,display_name,expires_at,can_add,revoked,created_at FROM gate_users WHERE event_id=? ORDER BY created_at DESC',(event_id,))]

@router.post('/events/{event_id}/gate-users/{user_id}/revoke')
def revoke_gate_user(event_id: str,user_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        c.execute('UPDATE gate_users SET revoked=1 WHERE id=? AND event_id=?',(user_id,event_id))
        if not c.execute('SELECT changes()').fetchone()[0]: raise HTTPException(404,'Zugang nicht gefunden')
        c.execute('DELETE FROM gate_sessions WHERE user_id=?',(user_id,))
    return {'ok':True}

@router.post('/gate/login')
def gate_login(data: GateLogin, request: Request):
    key=check_throttle(request,'gate')
    with database() as c:
        row=c.execute('SELECT * FROM gate_users WHERE username=?',(data.username.strip().lower(),)).fetchone()
    if not row or not hmac.compare_digest(password_digest(data.password,row['password_salt']),row['password_hash']) or row['revoked'] or row['expires_at']<=now():
        record_failure(key); raise HTTPException(401,'Ungültige oder abgelaufene Zugangsdaten')
    token=secrets.token_urlsafe(36)
    session_expiry=min(datetime.now(timezone.utc)+timedelta(hours=8),datetime.fromisoformat(row['expires_at']))
    with database() as c:
        c.execute('INSERT INTO gate_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],session_expiry.isoformat()))
    return {'token':token,'event_id':row['event_id'],'display_name':row['display_name'],'can_add':bool(row['can_add'])}

@router.get('/gate/{event_id}/overview')
def gate_overview(event_id: str,authorization: str | None = Header(default=None)):
    user=gate_user(authorization,event_id)
    with database() as c:
        ev=c.execute('SELECT title,start_date,end_date FROM events WHERE id=?',(event_id,)).fetchone()
        if not ev: raise HTTPException(404,'Event nicht gefunden')
        total=c.execute('SELECT COUNT(*) FROM participants WHERE event_id=?',(event_id,)).fetchone()[0]
        checked=c.execute('SELECT COUNT(DISTINCT participant_id) FROM checkins WHERE event_id=?',(event_id,)).fetchone()[0]
        today_count=c.execute('SELECT COUNT(*) FROM checkins WHERE event_id=? AND day=?',(event_id,str(today()))).fetchone()[0]
        rows=c.execute('''SELECT p.name,p.category,ch.day,ch.scanned_at FROM checkins ch
            JOIN participants p ON p.id=ch.participant_id WHERE ch.event_id=? ORDER BY ch.scanned_at DESC LIMIT 100''',(event_id,)).fetchall()
    return {'event':dict(ev),'total':total,'checked_unique':checked,'today':today_count,'checkins':[dict(r) for r in rows], 'can_add':bool(user['can_add'])}

# The same QR code is valid on every day of the event, once per day. Scans outside the event dates are refused.
def record_checkin(c,row,event_id,day=None):
    day=day or today()
    ev=c.execute('SELECT start_date,end_date FROM events WHERE id=?',(event_id,)).fetchone()
    start,end=date.fromisoformat(ev['start_date']),date.fromisoformat(ev['end_date'])
    if not start<=day<=end:
        raise HTTPException(400,f'Das Event findet am {day:%d.%m.%Y} nicht statt ({start:%d.%m.%Y} – {end:%d.%m.%Y})')
    try:
        c.execute('INSERT INTO checkins(participant_id,event_id,day,scanned_at) VALUES (?,?,?,?)',(row['id'],event_id,str(day),now()))
        status='checked_in'
    except sqlite3.IntegrityError: status='duplicate'
    attended=c.execute('SELECT COUNT(*) FROM checkins WHERE participant_id=?',(row['id'],)).fetchone()[0]
    return {'status':status,'name':row['name'],'category':row['category'],'day':str(day),
            'day_number':(day-start).days+1,'total_days':(end-start).days+1,'days_attended':attended}

@router.post('/gate/{event_id}/checkin')
def gate_checkin(event_id: str,data: GateScan,authorization: str | None = Header(default=None)):
    gate_user(authorization,event_id)
    data.qr_value=data.qr_value.strip()
    if not data.qr_value.startswith('EVP:'): raise HTTPException(400,'Kein gültiger EventPass-QR-Code')
    secret=data.qr_value[4:]
    with database() as c:
        row=c.execute('SELECT id,name,event_id,category FROM participants WHERE qr_secret=?',(secret,)).fetchone()
        if not row: raise HTTPException(404,'QR-Code unbekannt')
        if row['event_id']!=event_id: raise HTTPException(400,'Badge gehört zu einem anderen Event')
        return record_checkin(c,row,event_id,data.day)

@router.post('/gate/{event_id}/participants',status_code=201)
def gate_add_participant(event_id: str,data: ManualParticipant,request: Request,background: BackgroundTasks,authorization: str | None = Header(default=None)):
    gate_user(authorization,event_id,allow_add=True)
    if data.category not in ('Participant','Guest','Volunteer','Pastor','Speaker','VIP','Staff'):
        raise HTTPException(422,'Ungültige Rolle')
    pid=ident();secret=secrets.token_urlsafe(32)
    email=(data.email or '').strip().lower() or f'manual-{pid}@eventpass.invalid'
    with database() as c:
        if not c.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone(): raise HTTPException(404,'Event nicht gefunden')
        try: c.execute('INSERT INTO participants VALUES (?,?,?,?,?,?,?,?,?)',(pid,event_id,data.name.strip(),email,data.category,data.meal,'{}',secret,now()))
        except sqlite3.IntegrityError: raise HTTPException(409,'E-Mail bereits registriert')
    return {'participant_id':pid,'badge_secret':secret,'email_sent':queue_badge_email(background,pid,request)}

@router.get('/events/{event_id}/attendance')
def admin_attendance(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        total=c.execute('SELECT COUNT(*) FROM participants WHERE event_id=?',(event_id,)).fetchone()[0]
        checked=c.execute('SELECT COUNT(DISTINCT participant_id) FROM checkins WHERE event_id=?',(event_id,)).fetchone()[0]
        rows=c.execute('''SELECT p.name,p.category,ch.day,ch.scanned_at FROM checkins ch JOIN participants p ON p.id=ch.participant_id WHERE ch.event_id=? ORDER BY ch.scanned_at DESC LIMIT 200''',(event_id,)).fetchall()
    return {'registered':total,'present_unique':checked,'not_checked':total-checked,'checkins':[dict(r) for r in rows]}

class BadgeSettings(BaseModel):
    badge_width_mm: int = PydanticField(ge=45,le=200)
    badge_height_mm: int = PydanticField(ge=60,le=280)
    badge_heading: str = PydanticField(default="",max_length=120)
    badge_subtitle: str = PydanticField(default="WORSHIP  ·  WORD  ·  COMMUNITY  ·  IMPACT",max_length=140)
    badge_accent: str = PydanticField(default="",max_length=100)
    badge_date_label: str = PydanticField(default="",max_length=90)
    badge_location_label: str = PydanticField(default="",max_length=90)
    badge_qr_label: str = PydanticField(default="SCAN FOR CHECK-IN",max_length=90)

@router.patch('/events/{event_id}/badge-settings')
def update_badge_settings(event_id: str, data: BadgeSettings, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        result=c.execute('UPDATE events SET badge_width_mm=?,badge_height_mm=?,badge_heading=?,badge_subtitle=?,badge_accent=?,badge_date_label=?,badge_location_label=?,badge_qr_label=? WHERE id=?',(data.badge_width_mm,data.badge_height_mm,data.badge_heading,data.badge_subtitle,data.badge_accent,data.badge_date_label,data.badge_location_label,data.badge_qr_label,event_id))
        if not result.rowcount: raise HTTPException(404,'Event not found')
    return {'badge_width_mm':data.badge_width_mm,'badge_height_mm':data.badge_height_mm,'badge_heading':data.badge_heading,'badge_subtitle':data.badge_subtitle,'badge_accent':data.badge_accent,'badge_date_label':data.badge_date_label,'badge_location_label':data.badge_location_label,'badge_qr_label':data.badge_qr_label}

def logo_path():
    # Bundled with the backend so it also works in a container without the frontend sources.
    return BASE / 'default_logo.png'

def fit_text(pdf, text, max_width, initial_size, min_size=6, font=None):
    font = font or FONT_BOLD
    text=str(text or '')
    size=initial_size
    while size>min_size and pdf.stringWidth(text,font,size)>max_width: size-=0.5
    if pdf.stringWidth(text,font,size)>max_width:
        while text and pdf.stringWidth(text+'…',font,size)>max_width: text=text[:-1]
        text+='…'
    return text,size

def badge_asset(event_id, kind):
    return ASSETS_DIR / f'{event_id}-{kind}.png'

class ImageUpload(BaseModel):
    data_url: str = PydanticField(max_length=8_000_000)

@router.post('/events/{event_id}/badge-image/{kind}')
def upload_badge_image(event_id: str, kind: str, data: ImageUpload, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if kind not in ('background','logo'): raise HTTPException(400,'Unknown image type')
    with database() as c:
        if not c.execute('SELECT id FROM events WHERE id=?',(event_id,)).fetchone(): raise HTTPException(404,'Event not found')
    try:
        from PIL import Image
        raw=base64.b64decode(data.data_url.split(',',1)[-1],validate=True)
        if len(raw)>5_000_000: raise ValueError('Image too large')
        image=Image.open(io.BytesIO(raw));image.verify()
        image=Image.open(io.BytesIO(raw)).convert('RGBA')
        if image.width>5000 or image.height>5000: raise ValueError('Image dimensions too large')
        target=badge_asset(event_id,kind);target.parent.mkdir(parents=True,exist_ok=True)
        image.save(target,'PNG')
    except Exception as exc: raise HTTPException(422,f'Invalid image: {exc}')
    return {'ok':True}

@router.get('/public/events/{event_id}/badge-image/{kind}')
def get_badge_image(event_id: str,kind: str):
    if kind not in ('background','logo'): raise HTTPException(404,'Unknown image')
    target=badge_asset(event_id,kind)
    if not target.exists(): raise HTTPException(404,'No custom image')
    return Response(target.read_bytes(),media_type='image/png',headers={'Cache-Control':'no-store'})

def draw_badge(pdf, person, x, y, w, h):
    """Light, ink-saving badge. Keeps the existing layout and check-in QR."""
    pdf.saveState()
    pdf.setFillColor(HexColor('#FFFFFF'))
    pdf.rect(x,y,w,h,stroke=0,fill=1)
    art=badge_asset(person['event_id'],'background')
    if not art.exists(): art=BASE/'default_badge_bg.jpg'
    if not art.exists(): art=BASE.parent/'frontend'/'public'/'images'/'biblical-badge-bg.jpg'
    if art.exists():
        try:
            pdf.saveState()
            pdf.drawImage(ImageReader(str(art)),x,y,width=w,height=h,mask='auto')
            pdf.restoreState()
        except Exception: pass
    # Delicate footer rather than a full-bleed dark block.
    pdf.setFillColor(HexColor('#E5F2FF'))
    pdf.rect(x,y,w,h*.115,fill=1,stroke=0)
    pdf.setStrokeColor(HexColor('#D5B16D'))
    pdf.setLineWidth(.7)
    pdf.line(x+w*.08,y+h*.115,x+w*.92,y+h*.115)

    def center(value,yf,size,color='#113F76',maxw=.88,font=None):
        value=str(value or '').replace('\n',' ')
        if not value: return
        font=font or FONT_BOLD
        fitted,fs=fit_text(pdf,value,w*maxw,min(size,w*.14),min(4,size*.4),font=font)
        pdf.setFillColor(HexColor(color));pdf.setFont(font,fs)
        pdf.drawCentredString(x+w/2,y+h*yf,fitted)

    logo=badge_asset(person['event_id'],'logo')
    if not logo.exists(): logo=logo_path()
    if logo.exists():
        try:
            ir=ImageReader(str(logo));iw,ih=ir.getSize();sc=min(w*.18/iw,h*.095/ih)
            pdf.drawImage(ir,x+(w-iw*sc)/2,y+h*.84,width=iw*sc,height=ih*sc,mask='auto')
        except Exception: pass
    center(person['badge_heading'] or person['title'],.752,min(22,h*.055))
    center(person['badge_accent'],.690,min(18,h*.045),color='#A57832')
    center(person['badge_subtitle'],.637,min(7,h*.018),font=FONT_REGULAR)
    date_display=person['badge_date_label'] or (show_date(person['start_date'])+' – '+show_date(person['end_date']))
    center(date_display,.567,min(9,h*.022))
    center(person['badge_location_label'] or person['location'],.528,min(9,h*.022))
    pdf.setFillColor(HexColor('#FFFFFF'))
    pdf.setStrokeColor(HexColor('#DBEAF8'))
    pdf.roundRect(x+w*.08,y+h*.352,w*.84,h*.115,3*mm,stroke=1,fill=1)
    center(person['name'],.401,min(16,h*.039))
    qr=qrcode.make('EVP:'+person['qr_secret'],border=2).convert('RGB')
    qsize=min(w*.32,h*.145);qx=x+w*.20;qy=y+h*.183
    pdf.setFillColor(HexColor('#FFFFFF'))
    pdf.roundRect(qx-1.5*mm,qy-1.5*mm,qsize+3*mm,qsize+3*mm,2*mm,stroke=0,fill=1)
    pdf.drawImage(ImageReader(qr),qx,qy,width=qsize,height=qsize)
    label=person['badge_qr_label'] or 'SCAN FOR CHECK-IN'
    label_text,label_size=fit_text(pdf,label,w*.39,min(7,h*.018),4,font=FONT_BOLD)
    pdf.setFillColor(HexColor('#113F76'));pdf.setFont(FONT_BOLD,label_size)
    pdf.drawCentredString(x+w*.76,y+h*.245,label_text)
    center(person['category'].upper(),.062,min(16,h*.04),color='#113F76')
    pdf.restoreState()

def registration_url(event_id, url):
    # The browser knows the public address (domain, LAN IP, localhost); the server only checks it points to this event.
    parsed=urlparse(url)
    if len(url)>500 or parsed.scheme not in ('http','https') or not parsed.netloc or not parsed.path.endswith('/register/'+event_id):
        raise HTTPException(400,'Ungültiger Anmeldelink')
    with database() as c:
        event=c.execute('SELECT title,location,start_date,end_date FROM events WHERE id=?',(event_id,)).fetchone()
    if not event: raise HTTPException(404,'Event nicht gefunden')
    return event

def qr_image(value):
    q=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=12,border=4)
    q.add_data(value);q.make(fit=True)
    return q.make_image().convert('RGB')

@router.get('/public/events/{event_id}/registration-qr.png')
def registration_qr(event_id: str, url: str):
    registration_url(event_id,url)
    buf=io.BytesIO();qr_image(url).save(buf,format='PNG')
    return Response(buf.getvalue(),media_type='image/png',headers={'Content-Disposition':'inline; filename="anmeldung-qr.png"','Cache-Control':'no-store'})

@router.get('/public/events/{event_id}/registration-poster.pdf')
def registration_poster(event_id: str, url: str):
    event=registration_url(event_id,url)
    pagew,pageh=A4
    buf=io.BytesIO();pdf=canvas.Canvas(buf,pagesize=A4)
    def line(text,y,font,size,color='#113F76'):
        fitted,fs=fit_text(pdf,text,pagew-30*mm,size,8,font=font)
        pdf.setFillColor(HexColor(color));pdf.setFont(font,fs);pdf.drawCentredString(pagew/2,y,fitted)
    logo=logo_path()
    if logo.exists():
        try:
            ir=ImageReader(str(logo));iw,ih=ir.getSize();sc=min(32*mm/iw,32*mm/ih)
            pdf.drawImage(ir,(pagew-iw*sc)/2,pageh-48*mm,width=iw*sc,height=ih*sc,mask='auto')
        except Exception: pass
    line(event['title'],pageh-64*mm,FONT_BOLD,32)
    line(show_date(event['start_date'])+' – '+show_date(event['end_date'])+' · '+event['location'],pageh-76*mm,FONT_REGULAR,14,'#47617D')
    line('Jetzt anmelden · Register now',pageh-98*mm,FONT_BOLD,22,'#1764D8')
    size=120*mm
    pdf.drawImage(ImageReader(qr_image(url)),(pagew-size)/2,pageh-104*mm-size,width=size,height=size)
    line('QR-Code mit der Handykamera scannen · Scan with your phone camera',pageh-234*mm,FONT_REGULAR,12,'#47617D')
    line(url,pageh-244*mm,FONT_REGULAR,10,'#647892')
    pdf.showPage();pdf.save()
    return Response(buf.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="anmeldung-plakat.pdf"','Cache-Control':'no-store'})

BADGE_SQL='SELECT p.id,p.name,p.email,p.category,p.qr_secret,p.event_id,e.title,e.location,e.badge_width_mm,e.badge_height_mm,e.badge_heading,e.badge_subtitle,e.badge_accent,e.badge_date_label,e.badge_location_label,e.badge_qr_label,e.start_date,e.end_date FROM participants p JOIN events e ON e.id=p.event_id WHERE '
def single_badge_pdf(row):
    w=row['badge_width_mm']*mm;h=row['badge_height_mm']*mm
    buf=io.BytesIO();pdf=canvas.Canvas(buf,pagesize=(w,h))
    draw_badge(pdf,row,0,0,w,h);pdf.showPage();pdf.save()
    return buf.getvalue()

@router.get('/public/badge/{secret}/pdf')
def badge_pdf(secret: str):
    with database() as c: row=c.execute(BADGE_SQL+'p.qr_secret=?',(secret,)).fetchone()
    if not row: raise HTTPException(404,'Badge not found')
    return Response(single_badge_pdf(row),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="eventpass-badge.pdf"','Cache-Control':'no-store'})

# Badge by email after registration. Runs after the response, so a mail problem never blocks a registration.
def public_base(request: Request):
    if PUBLIC_URL: return PUBLIC_URL
    proto=request.headers.get('x-forwarded-proto',request.url.scheme).split(',')[0].strip()
    host=request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc
    return f'{proto}://{host}'

def queue_badge_email(background: BackgroundTasks, pid: str, request: Request):
    if not mailer.enabled(): return False
    with database() as c: row=c.execute('SELECT email FROM participants WHERE id=?',(pid,)).fetchone()
    if not row or row['email'].endswith('@eventpass.invalid'): return False
    background.add_task(send_badge_email,pid,public_base(request))
    return True

def badge_email(row, base):
    start,end=date.fromisoformat(row['start_date']),date.fromisoformat(row['end_date'])
    multi=start!=end
    dates=f'{start:%d.%m.} – {end:%d.%m.%Y}' if multi else f'{start:%d.%m.%Y}'
    link=f"{base}/api/eventpass/public/badge/{row['qr_secret']}/pdf"
    same_de=' Derselbe QR-Code gilt an allen Eventtagen.' if multi else ''
    same_en=' The same QR code is valid on every day of the event.' if multi else ''
    text=f"""Hallo {row['name']},

vielen Dank für deine Anmeldung zu {row['title']} ({dates}, {row['location']}).

Im Anhang findest du deinen Badge als PDF. Bitte bring ihn ausgedruckt oder auf dem Handy mit – der QR-Code wird beim Einlass gescannt.{same_de}

Badge herunterladen: {link}

---
Hello {row['name']},

thank you for registering for {row['title']} ({dates}, {row['location']}).
Your badge is attached as a PDF. Please bring it printed or on your phone; the QR code is scanned at the entrance.{same_en}

Download badge: {link}
"""
    e=lambda v: escape(str(v))
    html=f"""<div style="font-family:Arial,sans-serif;color:#173253;max-width:560px">
<h2 style="color:#1764d8">{e(row['title'])}</h2>
<p>Hallo {e(row['name'])},</p>
<p>vielen Dank für deine Anmeldung! 📍 {e(row['location'])} · {e(dates)}</p>
<p>Im Anhang findest du deinen <b>Badge als PDF</b>. Bitte bring ihn ausgedruckt oder auf dem Handy mit – der QR-Code wird beim Einlass gescannt.<b>{same_de}</b></p>
<p style="text-align:center"><img src="cid:qr" alt="QR-Code" width="200" height="200"></p>
<p style="text-align:center"><a href="{e(link)}" style="background:#1764d8;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:bold">Badge herunterladen</a></p>
<hr style="border:0;border-top:1px solid #dbeaf8">
<p style="color:#5b6f8c;font-size:13px">Hello {e(row['name'])}, thank you for registering. Your badge is attached as a PDF; please bring it printed or on your phone.{same_en}</p>
</div>"""
    qr=io.BytesIO();qrcode.make('EVP:'+row['qr_secret']).save(qr,format='PNG')
    return mailer.build(row['email'],f"Dein Badge für {row['title']} / Your badge",text,html,
                        attachments=[('badge.pdf',single_badge_pdf(row),'application','pdf')],inline_png=qr.getvalue())

def send_badge_email(pid: str, base: str):
    with database() as c: row=c.execute(BADGE_SQL+'p.id=?',(pid,)).fetchone()
    if not row: return
    try: mailer.deliver(badge_email(row,base)); status,error='sent',''
    except Exception as exc: status,error='failed',f'{type(exc).__name__}: {exc}'[:300]
    with database() as c:
        c.execute('INSERT OR REPLACE INTO badge_emails VALUES (?,?,?,?)',(pid,status,error,now()))

@router.post('/events/{event_id}/participants/{participant_id}/send-badge')
def resend_badge(event_id: str, participant_id: str, request: Request, background: BackgroundTasks, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if not mailer.enabled(): raise HTTPException(409,'E-Mail-Versand ist nicht eingerichtet (EVENTPASS_SMTP_HOST / EVENTPASS_MAIL_FROM)')
    with database() as c:
        row=c.execute('SELECT email FROM participants WHERE id=? AND event_id=?',(participant_id,event_id)).fetchone()
    if not row: raise HTTPException(404,'Teilnehmer nicht gefunden')
    if not queue_badge_email(background,participant_id,request): raise HTTPException(422,'Für diesen Teilnehmer ist keine E-Mail-Adresse hinterlegt')
    return {'queued':True}

class BadgeSelection(BaseModel):
    participant_ids: list[str] = PydanticField(min_length=1,max_length=2000)

@router.get('/events/{event_id}/badges/a4.pdf')
def badges_a4(event_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    return a4_sheet(event_id)

@router.post('/events/{event_id}/badges/a4.pdf')
def badges_a4_selected(event_id: str, data: BadgeSelection, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    return a4_sheet(event_id, set(data.participant_ids))

def a4_sheet(event_id, selected=None):
    with database() as c:
        event=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event: raise HTTPException(404,'Event not found')
        people=c.execute('SELECT p.id,p.name,p.category,p.qr_secret,p.event_id,e.title,e.location,e.badge_heading,e.badge_subtitle,e.badge_accent,e.badge_date_label,e.badge_location_label,e.badge_qr_label,e.start_date,e.end_date FROM participants p JOIN events e ON e.id=p.event_id WHERE p.event_id=? ORDER BY p.name',(event_id,)).fetchall()
    if selected is not None:
        people=[p for p in people if p['id'] in selected]
        if len(people)!=len(selected): raise HTTPException(400,'Mindestens ein ausgewählter Teilnehmer gehört nicht zu diesem Event')
    if not people: raise HTTPException(400,'Keine Teilnehmer vorhanden')
    w=event['badge_width_mm']*mm;h=event['badge_height_mm']*mm
    pagew,pageh=A4;margin=7*mm;gap=3*mm
    cols=int((pagew-2*margin+gap)//(w+gap));rows=int((pageh-2*margin+gap)//(h+gap))
    if cols<1 or rows<1: raise HTTPException(422,'Badge passt mit den aktuellen Maßen nicht auf A4. Bitte kleinere Maße wählen.')
    buf=io.BytesIO();pdf=canvas.Canvas(buf,pagesize=A4)
    perpage=cols*rows
    for i,p in enumerate(people):
        if i and i%perpage==0: pdf.showPage()
        slot=i%perpage;col=slot%cols;row=slot//cols
        x=margin+col*(w+gap);y=pageh-margin-h-row*(h+gap)
        draw_badge(pdf,p,x,y,w,h)
        pdf.setStrokeColor(HexColor('#AFC4DA'));pdf.setLineWidth(.35);pdf.rect(x,y,w,h,fill=0,stroke=1)
    pdf.showPage();pdf.save()
    return Response(buf.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="eventpass-a4-badges.pdf"','Cache-Control':'no-store'})

@router.get('/events/{event_id}/participants')
def participants(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        rows=c.execute('''SELECT p.id,p.name,p.email,p.category,p.meal,p.answers,p.qr_secret,p.created_at,m.status AS email_status,m.error AS email_error
          FROM participants p LEFT JOIN badge_emails m ON m.participant_id=p.id WHERE p.event_id=? ORDER BY p.created_at DESC''',(event_id,)).fetchall()
        return [{**dict(r),'answers':json.loads(r['answers'])} for r in rows]

# Responses as a spreadsheet (like the Google Forms answer sheet). Semicolon + BOM so Excel opens it directly.
@router.get('/events/{event_id}/participants.csv')
def participants_csv(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        event=c.execute('SELECT fields FROM events WHERE id=?',(event_id,)).fetchone()
        if not event: raise HTTPException(404,'Event nicht gefunden')
        rows=c.execute('''SELECT p.name,p.email,p.category,p.meal,p.answers,p.created_at,
          (SELECT GROUP_CONCAT(day,', ') FROM (SELECT day FROM checkins WHERE participant_id=p.id ORDER BY day)) AS days
          FROM participants p WHERE p.event_id=? ORDER BY p.created_at''',(event_id,)).fetchall()
    labels=[f['label'] for f in json.loads(event['fields'])]
    answers=[json.loads(r['answers']) for r in rows]
    labels+=sorted({k for a in answers for k in a}-set(labels))  # answers to fields removed later
    def cell(v):
        v=str(v or '')
        return "'"+v if v[:1] in ('=','+','-','@','\t','\r') else v  # no formula injection in Excel
    buf=io.StringIO();w=csv.writer(buf,delimiter=';')
    w.writerow(['Name','E-Mail','Kategorie','Verpflegung',*labels,'Registriert am','Eingecheckt'])
    for r,a in zip(rows,answers):
        email='' if r['email'].endswith('@eventpass.invalid') else r['email']
        w.writerow([cell(x) for x in (r['name'],email,r['category'],r['meal'],*(a.get(l,'') for l in labels),r['created_at'][:16].replace('T',' '),r['days'])])
    return Response('﻿'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="eventpass-antworten.csv"','Cache-Control':'no-store'})

@router.post('/events/{event_id}/checkin')
def checkin(event_id: str,data: Scan,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    data.qr_value=data.qr_value.strip()
    if not data.qr_value.startswith('EVP:'): raise HTTPException(400,'Invalid EventPass QR code')
    secret=data.qr_value[4:]
    with database() as c:
        row=c.execute('SELECT id,name,event_id,category FROM participants WHERE qr_secret=?',(secret,)).fetchone()
        if not row: raise HTTPException(404,'Unknown QR code')
        if row['event_id'] != event_id: raise HTTPException(400,'Badge belongs to a different event')
        return record_checkin(c,row,event_id,data.day)

@router.get('/events/{event_id}/stats')
def stats(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        total=c.execute('SELECT COUNT(*) FROM participants WHERE event_id=?',(event_id,)).fetchone()[0]
        by_day=[dict(r) for r in c.execute('SELECT day,COUNT(*) AS count FROM checkins WHERE event_id=? GROUP BY day ORDER BY day',(event_id,))]
    return {'registered':total,'checkins_by_day':by_day,'mail_enabled':mailer.enabled()}

# Canonical prefix behind the CMGI Apps reverse proxy; '/api' stays as a compatibility alias.
app.include_router(router, prefix='/api/eventpass')
app.include_router(router, prefix='/api', include_in_schema=False)
