import os, sqlite3, secrets, io, json, hashlib, hmac
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydanticField as PydanticField
import qrcode
from reportlab.pdfgen import canvas

BASE = Path(__file__).resolve().parent
DB = BASE / 'eventpass.sqlite3'
ADMIN_PASSWORD = os.getenv('EVENTPASS_ADMIN_PASSWORD', 'change-me-before-sharing')
ORIGIN = os.getenv('EVENTPASS_ORIGIN', 'http://localhost:5173')
app = FastAPI(title='EventPass Studio API', version='2.0')
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

@contextmanager
def database():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init():
    with database() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,title TEXT NOT NULL,location TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,fields TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY,event_id TEXT NOT NULL REFERENCES events(id),name TEXT NOT NULL,email TEXT NOT NULL,category TEXT NOT NULL,meal TEXT NOT NULL,answers TEXT NOT NULL,qr_secret TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,UNIQUE(event_id,email));
        CREATE TABLE IF NOT EXISTS checkins(id INTEGER PRIMARY KEY AUTOINCREMENT,participant_id TEXT NOT NULL REFERENCES participants(id),event_id TEXT NOT NULL REFERENCES events(id),day TEXT NOT NULL,scanned_at TEXT NOT NULL,UNIQUE(participant_id,day));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,expires_at TEXT NOT NULL);
        ''')
init()

def now(): return datetime.now(timezone.utc).isoformat()
def ident(): return secrets.token_urlsafe(12)
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
class PydanticField(BaseModel): label: str = PydanticPydanticField(min_length=1,max_length=80); required: bool = False
class EventIn(BaseModel):
    title: str = PydanticField(min_length=2,max_length=120)
    location: str = PydanticField(min_length=2,max_length=120)
    start_date: date
    end_date: date
    fields: list[Field] = PydanticField(default_factory=list,max_length=12)
class Registration(BaseModel):
    name: str = PydanticField(min_length=2,max_length=120)
    email: str = PydanticField(min_length=5,max_length=200)
    category: str = 'Participant'
    meal: str = 'Standard'
    answers: dict[str,str] = PydanticField(default_factory=dict)
class Scan(BaseModel): qr_value: str; day: date | None = None

@app.get('/api/health')
def health(): return {'ok': True}

@app.post('/api/login')
def login(data: Login):
    if not hmac.compare_digest(data.password,ADMIN_PASSWORD): raise HTTPException(401,'Incorrect password')
    token=secrets.token_urlsafe(36)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
    with database() as c: c.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),expiry))
    return {'token':token}

@app.get('/api/events')
def events(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c: return [event_row(r) for r in c.execute('SELECT * FROM events ORDER BY created_at DESC')]

@app.post('/api/events',status_code=201)
def create_event(data: EventIn,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if data.end_date < data.start_date: raise HTTPException(422,'End date before start date')
    if len({f.label.strip().lower() for f in data.fields}) != len(data.fields): raise HTTPException(422,'Field labels must be unique')
    event_id=ident()
    with database() as c:
        c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',(event_id,data.title.strip(),data.location.strip(),str(data.start_date),str(data.end_date),json.dumps([f.model_dump() for f in data.fields]),now()))
    return {'id':event_id}

@app.get('/api/public/events/{event_id}')
def public_event(event_id: str):
    with database() as c: row=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
    if not row: raise HTTPException(404,'Event not found')
    return event_row(row)

@app.post('/api/public/events/{event_id}/register',status_code=201)
def register(event_id: str,data: Registration):
    if data.category not in ('Participant','Guest','Volunteer'): raise HTTPException(422,'Invalid category')
    if data.meal not in ('Standard','Vegetarian','Vegan','Halal','No meal'): raise HTTPException(422,'Invalid meal')
    with database() as c:
        event=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event: raise HTTPException(404,'Event not found')
        fields=json.loads(event['fields'])
        if any(f['required'] and not data.answers.get(f['label'],'').strip() for f in fields): raise HTTPException(422,'Please fill all required fields')
        if any(k not in {f['label'] for f in fields} for k in data.answers): raise HTTPException(422,'Unknown field')
        pid=ident(); secret=secrets.token_urlsafe(32)
        try:
            c.execute('INSERT INTO participants VALUES (?,?,?,?,?,?,?,?,?)',(pid,event_id,data.name.strip(),data.email.strip().lower(),data.category,data.meal,json.dumps(data.answers),secret,now()))
        except sqlite3.IntegrityError: raise HTTPException(409,'This email is already registered for the event')
    return {'participant_id':pid,'badge_secret':secret}

@app.get('/api/public/badge/{secret}/qr.png')
def badge_qr(secret: str):
    with database() as c: row=c.execute('SELECT id FROM participants WHERE qr_secret=?',(secret,)).fetchone()
    if not row: raise HTTPException(404,'Badge not found')
    img=qrcode.make('EVP:'+secret)
    buf=io.BytesIO(); img.save(buf,format='PNG')
    return Response(buf.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})

@app.get('/api/public/badge/{secret}/pdf')
def badge_pdf(secret: str):
    with database() as c:
        row=c.execute('SELECT p.name,p.category,e.title,e.location,e.start_date,e.end_date FROM participants p JOIN events e ON e.id=p.event_id WHERE p.qr_secret=?',(secret,)).fetchone()
    if not row: raise HTTPException(404,'Badge not found')
    buf=io.BytesIO(); pdf=canvas.Canvas(buf,pagesize=(360,500))
    pdf.setFillColorRGB(.05,.09,.17); pdf.rect(0,0,360,500,fill=1,stroke=0)
    pdf.setFillColorRGB(.89,.71,.33)
    def line(text,y,size=15):
        pdf.setFont('Helvetica-Bold',size); pdf.drawCentredString(180,y,str(text)[:38])
    line('EVENTPASS STUDIO',454,17); line(row['title'],409,20)
    pdf.setFillColorRGB(1,1,1); line(row['name'],354,19); line(row['category'],326,13)
    qr=qrcode.make('EVP:'+secret).convert('RGB'); from reportlab.lib.utils import ImageReader
    pdf.drawImage(ImageReader(qr),95,106,width=170,height=170)
    line(row['location'],78,12); line(row['start_date']+'  -  '+row['end_date'],55,11)
    pdf.showPage(); pdf.save()
    return Response(buf.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="eventpass-badge.pdf"','Cache-Control':'no-store'})

@app.get('/api/events/{event_id}/participants')
def participants(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        rows=c.execute('SELECT id,name,email,category,meal,answers,qr_secret,created_at FROM participants WHERE event_id=? ORDER BY created_at DESC',(event_id,)).fetchall()
        return [{**dict(r),'answers':json.loads(r['answers'])} for r in rows]

@app.post('/api/events/{event_id}/checkin')
def checkin(event_id: str,data: Scan,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    if not data.qr_value.startswith('EVP:'): raise HTTPException(400,'Invalid EventPass QR code')
    secret=data.qr_value[4:]
    with database() as c:
        row=c.execute('SELECT id,name,event_id FROM participants WHERE qr_secret=?',(secret,)).fetchone()
        if not row: raise HTTPException(404,'Unknown QR code')
        if row['event_id'] != event_id: raise HTTPException(400,'Badge belongs to a different event')
        day=str(data.day or date.today())
        try: c.execute('INSERT INTO checkins(participant_id,event_id,day,scanned_at) VALUES (?,?,?,?)',(row['id'],event_id,day,now()))
        except sqlite3.IntegrityError: return {'status':'duplicate','name':row['name'],'day':day}
    return {'status':'checked_in','name':row['name'],'day':day}

@app.get('/api/events/{event_id}/stats')
def stats(event_id: str,authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with database() as c:
        total=c.execute('SELECT COUNT(*) FROM participants WHERE event_id=?',(event_id,)).fetchone()[0]
        by_day=[dict(r) for r in c.execute('SELECT day,COUNT(*) AS count FROM checkins WHERE event_id=? GROUP BY day ORDER BY day',(event_id,))]
    return {'registered':total,'checkins_by_day':by_day}

