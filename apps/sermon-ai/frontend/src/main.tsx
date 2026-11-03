import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { auth, BASE, PORTAL, PORTAL_ROOT, request, type Me } from './api';
import { Link, usePath } from './router';
import { pump } from './uploadQueue';
import { useQueue } from './useQueue';
import { SermonList } from './pages/SermonList';
import { RecordPage } from './pages/RecordPage';
import { SermonPage } from './pages/SermonPage';
import './styles.css';


// ---------------------------------------------------------------- login

function Login({ onDone }: { onDone: () => void }) {
  const next = encodeURIComponent(window.location.pathname);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { token } = await request<{ token: string }>('/login', { method: 'POST', body: { password } });
      auth.set(token);
      onDone();
      void pump(); // uploads that waited for a login continue now
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="container narrow">
      <section className="card">
        <h1>Sign in</h1>
        <p className="muted">Sign in with your <b>CMGI account</b> — one account for all CMGI apps. New accounts get 5 free minutes of transcription.</p>
        <a className="btn btn-primary" href={`${PORTAL_ROOT}/login?next=${next}`}>Sign in with CMGI account</a>
        <p className="muted small">No account yet? <a href={`${PORTAL_ROOT}/register?next=${next}`}>Create one for free</a>.</p>
        <details className="legacy-login">
          <summary>Sign in with the old Sermon Intelligence password</summary>
          <form onSubmit={submit}>
            <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            {error && <p className="alert error">{error}</p>}
            <button className="btn btn-ghost" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          </form>
        </details>
      </section>
    </main>
  );
}

// ---------------------------------------------------------------- shell

function App() {
  const path = usePath();
  const queue = useQueue();
  // undefined while checking, null when nobody is signed in.
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const loadMe = () => request<Me>('/me').then(setMe, () => setMe(null));
  useEffect(() => {
    void loadMe();
    window.addEventListener('sermon-auth', loadMe);
    const timer = window.setInterval(loadMe, 60_000);  // keeps the remaining AI minutes current
    return () => { window.removeEventListener('sermon-auth', loadMe); window.clearInterval(timer); };
  }, []);
  async function signOut() {
    if (me?.legacy) auth.clear();
    else await fetch('/api/accounts/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => undefined);
    setMe(null);
  }

  const parts = path.split('/').filter(Boolean); // ['sermons', id, 'record']
  let page = <SermonList />;
  if (parts[0] === 'sermons' && parts[1]) page = parts[2] === 'record' ? <RecordPage id={parts[1]} key={parts[1]} /> : <SermonPage id={parts[1]} key={parts[1]} />;

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="brand">
            <img src={`${BASE}/cmgi-logo.png`} alt="" width={34} height={34} />
            <span>Sermon <b>Intelligence</b></span>
          </Link>
          <div className="topbar-actions">
            {queue && queue.pending > 0 && (
              <span className={`pill ${queue.offline ? 'pill-warn' : 'pill-info'}`} title="Recorded audio waiting to be uploaded">
                {queue.offline ? 'Offline · ' : 'Uploading · '}{queue.pending} part{queue.pending === 1 ? '' : 's'} saved on this device
              </span>
            )}
            {me && me.billed && (
              <a className={`pill ${me.ai_credit_seconds < 120 ? 'pill-warn' : 'pill-info'}`} href={navigator.userAgent.includes('CMGIApp') ? undefined : `${PORTAL_ROOT}/pricing`} title="AI transcription time left in your CMGI account">
                AI time: {Math.floor(me.ai_credit_seconds / 60)} min left
              </a>
            )}
            <a className="ghost-link" href={PORTAL}>← CMGI Apps</a>
            {me && <a className="ghost-link" href={`${PORTAL_ROOT}/account`}>{me.name}</a>}
            {me && <button className="ghost-link" onClick={() => void signOut()}>Sign out</button>}
          </div>
        </div>
      </header>
      {queue?.error && <div className="container"><p className="alert error">{queue.error}</p></div>}
      {me ? page : me === undefined ? <main className="container narrow"><p className="muted">Checking sign-in …</p></main> : <Login onDone={() => void loadMe()} />}
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
