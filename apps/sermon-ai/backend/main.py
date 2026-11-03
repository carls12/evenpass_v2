"""Sermon Intelligence API — record sermons in the browser, transcribe, report and translate them."""
import hashlib, hmac, json, math, os, secrets, shutil, sqlite3, threading, time
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import ai
import backup
import cmgi_auth
import export

BASE = Path(__file__).resolve().parent
ENV = os.getenv('SERMON_ENV', 'development')
DB = Path(os.getenv('SERMON_DB_PATH', str(BASE / 'sermon.sqlite3')))
AUDIO_DIR = Path(os.getenv('SERMON_AUDIO_DIR', str(DB.parent / 'audio')))
DEV_DEFAULT_PASSWORD = 'change-me-before-sharing'
ADMIN_PASSWORD = os.getenv('SERMON_ADMIN_PASSWORD', '')
if ENV == 'production' and (len(ADMIN_PASSWORD) < 12 or ADMIN_PASSWORD == DEV_DEFAULT_PASSWORD):
    raise RuntimeError('SERMON_ADMIN_PASSWORD must be set (min. 12 characters) in production')
ADMIN_PASSWORD = ADMIN_PASSWORD or DEV_DEFAULT_PASSWORD
ORIGINS = [o.strip() for o in os.getenv('SERMON_ORIGIN', 'http://localhost:5173,http://localhost:5175').split(',') if o.strip()]

MAX_CHUNK_BYTES = 5_000_000
MAX_SEGMENT_BYTES = 24_000_000  # OpenAI accepts up to 25 MB per transcription request
AUDIO_TYPES = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'mp4', 'audio/mpeg': 'mp3', 'audio/wav': 'wav'}

docs = ENV != 'production'
app = FastAPI(title='Sermon Intelligence API', version='0.1',
              docs_url='/api/sermon-ai/docs' if docs else None, redoc_url=None,
              openapi_url='/api/sermon-ai/openapi.json' if docs else None)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=False, allow_methods=['*'], allow_headers=['*'])
router = APIRouter()
current_request: ContextVar[Request | None] = ContextVar('current_request', default=None)


@app.middleware('http')
async def remember_request(request: Request, call_next):
    # Lets require_admin() read the CMGI session cookie without changing every endpoint signature.
    token = current_request.set(request)
    try:
        return await call_next(request)
    finally:
        current_request.reset(token)


def now(): return datetime.now(timezone.utc).isoformat()
def ident(): return secrets.token_urlsafe(12)


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


def init():
    with database() as c:
        existing = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sermons'").fetchone()
        cols = {r[1] for r in c.execute('PRAGMA table_info(sermons)')}
    if existing and 'owner_id' not in cols:
        backup.backup(DB, AUDIO_DIR, Path(os.getenv('SERMON_BACKUP_DIR', str(DB.parent / 'backups'))) / 'pre-migration')
    with database() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sermons(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, preacher TEXT NOT NULL DEFAULT '', sermon_date TEXT NOT NULL,
          language TEXT NOT NULL DEFAULT 'auto', status TEXT NOT NULL, progress TEXT NOT NULL DEFAULT '',
          error TEXT NOT NULL DEFAULT '', duration_s INTEGER NOT NULL DEFAULT 0, transcript TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS segments(
          sermon_id TEXT NOT NULL REFERENCES sermons(id) ON DELETE CASCADE, idx INTEGER NOT NULL, mime TEXT NOT NULL,
          next_seq INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0,
          transcript TEXT, PRIMARY KEY(sermon_id, idx));
        CREATE TABLE IF NOT EXISTS outputs(
          sermon_id TEXT NOT NULL REFERENCES sermons(id) ON DELETE CASCADE, kind TEXT NOT NULL, language TEXT NOT NULL,
          content TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(sermon_id, kind, language));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
        ''')
        # Jobs run in-process; a restart interrupts them. Put those sermons back into a retryable state.
        c.execute("UPDATE sermons SET status='recorded', progress='', error='Transcription was interrupted by a server restart. Please start it again.' WHERE status='transcribing'")
        c.execute("UPDATE sermons SET status='transcribed', progress='', error='Analysis was interrupted by a server restart. Please start it again.' WHERE status='analyzing'")
        # Owner = CMGI account id. '' = recorded before CMGI accounts existed: belongs to the platform admins.
        if 'owner_id' not in {r[1] for r in c.execute('PRAGMA table_info(sermons)')}:
            c.execute("ALTER TABLE sermons ADD COLUMN owner_id TEXT NOT NULL DEFAULT ''")
        c.execute('DELETE FROM sessions WHERE expires_at<?', (now(),))


init()

# ---------------------------------------------------------------- auth

LOGIN_LIMIT = int(os.getenv('SERMON_LOGIN_LIMIT', '10'))
LOGIN_WINDOW = 15 * 60
login_failures: dict[str, list[float]] = {}


# The legacy password login stays until everyone uses CMGI accounts (SERMON_LEGACY_ADMIN=false turns it off).
LEGACY_ADMIN = os.getenv('SERMON_LEGACY_ADMIN', 'true').lower() != 'false'
LEGACY_ACTOR = {'id': '', 'email': '', 'name': 'Sermon admin', 'is_admin': True, 'pro': True, 'ai_credit_seconds': 0, 'legacy': True}


def legacy_session(token: str):
    if not LEGACY_ADMIN:
        return False
    with database() as c:
        row = c.execute('SELECT expires_at FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return bool(row and row['expires_at'] >= now())


def require_admin(authorization: str | None, sermon_id: str | None = None):
    """Signed-in CMGI account (cookie or Bearer) or legacy admin; with sermon_id only its owner or a platform admin."""
    token = authorization[7:].strip() if authorization and authorization.startswith('Bearer ') else None
    if token and legacy_session(token):
        actor = LEGACY_ACTOR
    else:
        request = current_request.get()
        cookie = request.cookies.get('cmgi_session') if request else None
        account = cmgi_auth.account_for_token(token or cookie)
        if not account and token and cookie and cookie != token:
            account = cmgi_auth.account_for_token(cookie)
        if not account:
            raise HTTPException(401, 'Please sign in with your CMGI account')
        actor = {**account, 'legacy': False}
    if sermon_id is not None:
        with database() as c:
            row = c.execute('SELECT owner_id FROM sermons WHERE id=?', (sermon_id,)).fetchone()
        if not row or not (actor['is_admin'] or row['owner_id'] == actor['id']):
            raise HTTPException(404, 'Sermon not found')
    return actor


# ---- AI minutes: transcription is paid with the owner's CMGI credit ----
BYTES_PER_SECOND = 4000  # the recorder uses 32 kbit/s


def billed_user(owner_id: str):
    """Whose credit pays: nobody for sermons from before accounts or of platform admins."""
    if not owner_id:
        return None
    owner = cmgi_auth.account_by_id(owner_id)
    return None if owner and owner.get('is_admin') else owner_id


def estimate_seconds(nbytes: int):
    return max(1, math.ceil(nbytes / BYTES_PER_SECOND))


class Login(BaseModel):
    password: str


@router.get('/health')
def health():
    with database() as c:
        c.execute('SELECT 1').fetchone()
    return {'ok': True}


@router.post('/login')
def login(data: Login, request: Request):
    key = request.client.host if request.client else 'unknown'
    t = time.monotonic()
    recent = [x for x in login_failures.get(key, []) if t - x < LOGIN_WINDOW]
    login_failures[key] = recent
    if len(recent) >= LOGIN_LIMIT:
        raise HTTPException(429, 'Too many failed attempts. Please try again in 15 minutes.')
    if not hmac.compare_digest(data.password.encode(), ADMIN_PASSWORD.encode()):
        recent.append(t)
        raise HTTPException(401, 'Incorrect password')
    token = secrets.token_urlsafe(36)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    with database() as c:
        c.execute('INSERT INTO sessions VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(), expiry))
    return {'token': token}


@router.get('/status')
def service_status(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    return ai.status()


@router.get('/me')
def me(authorization: str | None = Header(default=None)):
    """Who is signed in and how many AI minutes are left (admins are not billed)."""
    actor = require_admin(authorization)
    return {'name': actor['name'], 'email': actor['email'], 'is_admin': actor['is_admin'], 'legacy': actor['legacy'],
            'billed': not actor['is_admin'], 'ai_credit_seconds': actor.get('ai_credit_seconds', 0)}

# ---------------------------------------------------------------- sermons


class SermonIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    preacher: str = Field(default='', max_length=120)
    sermon_date: date
    language: str = 'auto'


class SermonPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    preacher: str | None = Field(default=None, max_length=120)
    sermon_date: date | None = None
    language: str | None = None
    transcript: str | None = Field(default=None, max_length=400_000)


def check_language(value: str | None):
    if value is not None and value not in ('auto', *ai.LANGUAGES):
        raise HTTPException(422, 'Language must be auto, en, fr or de')


def get_sermon(c, sermon_id: str):
    row = c.execute('SELECT * FROM sermons WHERE id=?', (sermon_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Sermon not found')
    return row


def sermon_dir(sermon_id: str) -> Path:
    return AUDIO_DIR / sermon_id


def segment_path(sermon_id: str, idx: int, mime: str) -> Path:
    return sermon_dir(sermon_id) / f'{idx:03d}.{AUDIO_TYPES[mime]}'


@router.get('/sermons')
def list_sermons(authorization: str | None = Header(default=None)):
    actor = require_admin(authorization)
    mine = '' if actor['is_admin'] else 'WHERE s.owner_id=?'
    with database() as c:
        rows = c.execute('''SELECT s.id, s.title, s.preacher, s.sermon_date, s.language, s.status, s.progress, s.error,
                                   s.duration_s, s.created_at, (SELECT GROUP_CONCAT(language) FROM outputs o
                                   WHERE o.sermon_id=s.id AND o.kind='report') AS report_languages
                            FROM sermons s ''' + mine + ' ORDER BY s.sermon_date DESC, s.created_at DESC',
                         () if actor['is_admin'] else (actor['id'],)).fetchall()
    return [dict(r) for r in rows]


@router.post('/sermons', status_code=201)
def create_sermon(data: SermonIn, authorization: str | None = Header(default=None)):
    actor = require_admin(authorization)
    check_language(data.language)
    sermon_id = ident()
    with database() as c:
        c.execute('INSERT INTO sermons(id,title,preacher,sermon_date,language,status,created_at,updated_at,owner_id) VALUES (?,?,?,?,?,?,?,?,?)',
                  (sermon_id, data.title.strip(), data.preacher.strip(), str(data.sermon_date), data.language, 'recording', now(), now(), actor['id']))
    return {'id': sermon_id}


@router.get('/sermons/{sermon_id}')
def sermon_detail(sermon_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    with database() as c:
        sermon = dict(get_sermon(c, sermon_id))
        sermon['segments'] = [dict(r) for r in c.execute(
            'SELECT idx, mime, bytes, complete, transcript IS NOT NULL AS transcribed FROM segments WHERE sermon_id=? ORDER BY idx', (sermon_id,))]
        outputs = c.execute('SELECT kind, language, content, model, created_at FROM outputs WHERE sermon_id=? ORDER BY language', (sermon_id,))
        sermon['outputs'] = [{**dict(r), 'content': json.loads(r['content']) if r['kind'] == 'report' else r['content']} for r in outputs]
    return sermon


@router.patch('/sermons/{sermon_id}')
def update_sermon(sermon_id: str, data: SermonPatch, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    check_language(data.language)
    changes = {k: (str(v) if isinstance(v, date) else v) for k, v in data.model_dump(exclude_none=True).items()}
    if not changes:
        return {'ok': True}
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        if sermon['status'] in ('transcribing', 'analyzing'):
            raise HTTPException(409, 'Please wait until processing has finished')
        if 'transcript' in changes and sermon['status'] in ('recording', 'recorded') and changes['transcript'].strip():
            changes['status'] = 'transcribed'
        sets = ', '.join(f'{k}=?' for k in changes)
        c.execute(f'UPDATE sermons SET {sets}, updated_at=? WHERE id=?', (*changes.values(), now(), sermon_id))
    return {'ok': True}


@router.delete('/sermons/{sermon_id}')
def delete_sermon(sermon_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        if sermon['status'] in ('transcribing', 'analyzing'):
            raise HTTPException(409, 'Please wait until processing has finished')
        c.execute('DELETE FROM sermons WHERE id=?', (sermon_id,))
    shutil.rmtree(sermon_dir(sermon_id), ignore_errors=True)
    return {'ok': True}

# ---------------------------------------------------------------- recording upload


@router.put('/sermons/{sermon_id}/segments/{idx}/chunks/{seq}')
async def upload_chunk(sermon_id: str, idx: int, seq: int, request: Request, authorization: str | None = Header(default=None)):
    """Append one recorder chunk. Chunks arrive in order; a repeated chunk (client retry) is acknowledged, not stored twice."""
    require_admin(authorization, sermon_id)
    mime = (request.headers.get('content-type') or '').split(';')[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(415, f'Unsupported audio type: {mime or "none"}')
    if not 0 <= idx < 1000 or seq < 0:
        raise HTTPException(422, 'Invalid segment or chunk number')
    body = await request.body()
    if len(body) > MAX_CHUNK_BYTES:
        raise HTTPException(413, 'Chunk too large')
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        if sermon['status'] != 'recording':
            raise HTTPException(409, 'This sermon is not recording')
        segment = c.execute('SELECT * FROM segments WHERE sermon_id=? AND idx=?', (sermon_id, idx)).fetchone()
        if not segment:
            c.execute('INSERT INTO segments(sermon_id, idx, mime) VALUES (?,?,?)', (sermon_id, idx, mime))
            segment = {'next_seq': 0, 'bytes': 0, 'mime': mime}
        if seq < segment['next_seq']:
            return {'next_seq': segment['next_seq'], 'duplicate': True}
        if seq > segment['next_seq']:
            raise HTTPException(409, f"Missing chunk {segment['next_seq']} before {seq}")
        if segment['bytes'] + len(body) > MAX_SEGMENT_BYTES:
            raise HTTPException(413, 'Segment too large')
        path = segment_path(sermon_id, idx, segment['mime'])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'ab') as f:
            f.write(body)
        c.execute('UPDATE segments SET next_seq=next_seq+1, bytes=bytes+? WHERE sermon_id=? AND idx=?', (len(body), sermon_id, idx))
    return {'next_seq': seq + 1}


@router.post('/sermons/{sermon_id}/segments/{idx}/complete')
def complete_segment(sermon_id: str, idx: int, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    with database() as c:
        get_sermon(c, sermon_id)
        c.execute('UPDATE segments SET complete=1 WHERE sermon_id=? AND idx=?', (sermon_id, idx))
    return {'ok': True}


class Finish(BaseModel):
    duration_s: int = Field(ge=0, le=6 * 3600)


@router.post('/sermons/{sermon_id}/finish')
def finish_recording(sermon_id: str, data: Finish, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        if sermon['status'] != 'recording':
            return {'ok': True}  # repeated finish from the upload queue
        if not c.execute('SELECT 1 FROM segments WHERE sermon_id=? AND bytes>0', (sermon_id,)).fetchone():
            raise HTTPException(422, 'No audio has been uploaded for this sermon yet')
        c.execute("UPDATE sermons SET status='recorded', duration_s=MAX(duration_s, ?), error='', updated_at=? WHERE id=?",
                  (data.duration_s, now(), sermon_id))
    return {'ok': True}


@router.post('/sermons/{sermon_id}/resume')
def resume_recording(sermon_id: str, authorization: str | None = Header(default=None)):
    """Record more audio after the recording was finished (e.g. stopped too early)."""
    require_admin(authorization, sermon_id)
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        if sermon['status'] not in ('recording', 'recorded'):
            raise HTTPException(409, 'Recording can only be continued before transcription')
        c.execute("UPDATE sermons SET status='recording', updated_at=? WHERE id=?", (now(), sermon_id))
        last = c.execute('SELECT MAX(idx) FROM segments WHERE sermon_id=?', (sermon_id,)).fetchone()[0]
    return {'next_segment': 0 if last is None else last + 1}


@router.get('/sermons/{sermon_id}/segments/{idx}/audio')
def segment_audio(sermon_id: str, idx: int, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    with database() as c:
        segment = c.execute('SELECT mime FROM segments WHERE sermon_id=? AND idx=?', (sermon_id, idx)).fetchone()
    if not segment or not segment_path(sermon_id, idx, segment['mime']).exists():
        raise HTTPException(404, 'Audio not found')
    return Response(segment_path(sermon_id, idx, segment['mime']).read_bytes(), media_type=segment['mime'])

# ---------------------------------------------------------------- processing jobs


def set_state(sermon_id: str, **fields):
    sets = ', '.join(f'{k}=?' for k in fields)
    with database() as c:
        c.execute(f'UPDATE sermons SET {sets}, updated_at=? WHERE id=?', (*fields.values(), now(), sermon_id))


def claim(sermon_id: str, allowed: tuple[str, ...], new_status: str) -> sqlite3.Row:
    """Atomically move a sermon into a running state, so the same job never runs twice."""
    with database() as c:
        sermon = get_sermon(c, sermon_id)
        marks = ','.join('?' * len(allowed))
        updated = c.execute(f"UPDATE sermons SET status=?, error='', progress='Starting…', updated_at=? WHERE id=? AND status IN ({marks})",
                            (new_status, now(), sermon_id, *allowed)).rowcount
        if not updated:
            raise HTTPException(409, f"Not possible while the sermon is '{sermon['status']}'")
    return sermon


def run_transcription(sermon_id: str, payer: str | None = None, run: str = ''):
    """payer: CMGI account whose AI minutes pay (None = not billed). Each part is booked BEFORE it is sent to
    OpenAI (estimated from the file size) and settled afterwards with the exact length OpenAI reports."""
    try:
        with database() as c:
            sermon = get_sermon(c, sermon_id)
            segments = c.execute('SELECT idx, mime, bytes, transcript FROM segments WHERE sermon_id=? AND bytes>0 ORDER BY idx', (sermon_id,)).fetchall()
        language = None if sermon['language'] == 'auto' else sermon['language']
        texts = []
        for n, seg in enumerate(segments, 1):
            set_state(sermon_id, progress=f'Transcribing part {n} of {len(segments)}')
            text = seg['transcript']
            if text is None:  # parts done before an error are kept, so a retry only pays for the rest
                ref = f"sermon:{sermon_id}:{run}:{seg['idx']}"
                booked = estimate_seconds(seg['bytes'])
                if payer:
                    try:
                        cmgi_auth.consume_credit(payer, booked, ref, f"{sermon['title']} · part {n}")
                    except cmgi_auth.NotEnoughCredit:
                        raise ai.AIError(f'Your AI minutes are used up (part {n} of {len(segments)} needs about {math.ceil(booked / 60)} min). '
                                         'Buy more minutes in your CMGI account, then start the transcription again — finished parts are kept.')
                result = ai.transcribe(segment_path(sermon_id, seg['idx'], seg['mime']), seg['mime'], language, ' '.join(texts))
                text, actual = result if isinstance(result, tuple) else (result, None)
                if payer and actual:
                    diff = math.ceil(actual) - booked
                    try:
                        if diff > 0: cmgi_auth.consume_credit(payer, diff, ref + ':extra', 'exact length')
                        elif diff < 0: cmgi_auth.refund_credit(payer, -diff, ref + ':refund', 'exact length')
                    except (cmgi_auth.NotEnoughCredit, HTTPException):
                        pass  # small difference; the part is already transcribed
                with database() as c:
                    c.execute('UPDATE segments SET transcript=? WHERE sermon_id=? AND idx=?', (text, sermon_id, seg['idx']))
            texts.append(text)
        set_state(sermon_id, status='transcribed', progress='', transcript='\n\n'.join(t for t in texts if t))
    except ai.AIError as e:
        set_state(sermon_id, status='recorded', progress='', error=str(e))
    except HTTPException as e:  # accounts service not reachable for the booking
        set_state(sermon_id, status='recorded', progress='', error=str(e.detail))
    except Exception as e:  # unexpected: keep the sermon retryable and surface the message
        set_state(sermon_id, status='recorded', progress='', error=f'Transcription failed: {e}')


def run_analysis(sermon_id: str, languages: list[str], translate: bool):
    try:
        with database() as c:
            sermon = dict(get_sermon(c, sermon_id))
        steps = [('report', lang) for lang in languages]
        steps += [('translation', lang) for lang in languages if translate and lang != sermon['language']]
        for n, (kind, lang) in enumerate(steps, 1):
            set_state(sermon_id, progress=f"{'Report' if kind == 'report' else 'Translation'} · {ai.LANGUAGES[lang]} ({n}/{len(steps)})")
            if kind == 'report':
                content = json.dumps(ai.generate_report(sermon['transcript'], sermon, lang), ensure_ascii=False)
            else:
                content = ai.translate(sermon['transcript'], sermon, lang)
            with database() as c:
                c.execute('INSERT OR REPLACE INTO outputs VALUES (?,?,?,?,?,?)', (sermon_id, kind, lang, content, ai.CLAUDE_MODEL, now()))
        set_state(sermon_id, status='done', progress='')
    except ai.AIError as e:
        set_state(sermon_id, status='transcribed', progress='', error=str(e))
    except Exception as e:
        set_state(sermon_id, status='transcribed', progress='', error=f'Analysis failed: {e}')


def start(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


@router.post('/sermons/{sermon_id}/transcribe', status_code=202)
def transcribe(sermon_id: str, authorization: str | None = Header(default=None)):
    actor = require_admin(authorization, sermon_id)
    with database() as c:
        if not c.execute('SELECT 1 FROM segments WHERE sermon_id=? AND bytes>0', (sermon_id,)).fetchone():
            get_sermon(c, sermon_id)
            raise HTTPException(422, 'There is no audio to transcribe')
        sermon = get_sermon(c, sermon_id)
        fresh = sermon['status'] in ('transcribed', 'done')
        pending = c.execute('SELECT COALESCE(SUM(bytes),0) FROM segments WHERE sermon_id=? AND bytes>0' + ('' if fresh else ' AND transcript IS NULL'),
                            (sermon_id,)).fetchone()[0]
    payer = billed_user(sermon['owner_id'])
    if payer:
        needed = estimate_seconds(pending)
        balance = (actor if actor['id'] == payer else cmgi_auth.account_by_id(payer) or {}).get('ai_credit_seconds', 0)
        if balance < needed:
            raise HTTPException(402, f'This recording needs about {math.ceil(needed / 60)} min of AI time, '
                                     f'you have {balance // 60} min {balance % 60} s left. Buy more minutes in your CMGI account.')
    if fresh:  # a fresh run re-transcribes everything; cached part transcripts only help retries after an error
        with database() as c:
            c.execute('UPDATE segments SET transcript=NULL WHERE sermon_id=?', (sermon_id,))
    claim(sermon_id, ('recorded', 'transcribed', 'done'), 'transcribing')
    start(run_transcription, sermon_id, payer, secrets.token_hex(4))
    return {'status': 'transcribing'}


class AnalyzeIn(BaseModel):
    languages: list[str] = Field(min_length=1, max_length=3)
    translate: bool = False


@router.post('/sermons/{sermon_id}/analyze', status_code=202)
def analyze(sermon_id: str, data: AnalyzeIn, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    languages = list(dict.fromkeys(data.languages))
    if any(lang not in ai.LANGUAGES for lang in languages):
        raise HTTPException(422, 'Languages must be en, fr or de')
    with database() as c:
        if not get_sermon(c, sermon_id)['transcript'].strip():
            raise HTTPException(422, 'Transcribe the sermon (or enter a transcript) first')
    claim(sermon_id, ('transcribed', 'done'), 'analyzing')
    start(run_analysis, sermon_id, languages, data.translate)
    return {'status': 'analyzing'}

# ---------------------------------------------------------------- export


@router.get('/sermons/{sermon_id}/export/{language}.{fmt}')
def export_report(sermon_id: str, language: str, fmt: str, authorization: str | None = Header(default=None)):
    require_admin(authorization, sermon_id)
    if fmt not in ('pdf', 'md'):
        raise HTTPException(404, 'Unknown format')
    with database() as c:
        sermon = dict(get_sermon(c, sermon_id))
        report = c.execute("SELECT content FROM outputs WHERE sermon_id=? AND kind='report' AND language=?", (sermon_id, language)).fetchone()
        translation = c.execute("SELECT content FROM outputs WHERE sermon_id=? AND kind='translation' AND language=?", (sermon_id, language)).fetchone()
    if not report:
        raise HTTPException(404, 'No report in this language yet')
    data = json.loads(report['content'])
    text = translation['content'] if translation else None
    name = f"sermon-{sermon['sermon_date']}-{language}.{fmt}"
    headers = {'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'no-store'}
    if fmt == 'md':
        return Response(export.markdown(sermon, data, language, text), media_type='text/markdown; charset=utf-8', headers=headers)
    return Response(export.pdf(sermon, data, language, text), media_type='application/pdf', headers=headers)


app.include_router(router, prefix='/api/sermon-ai')
