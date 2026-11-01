import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { auth, BASE, PORTAL, request } from './api';
import { Link, usePath } from './router';
import { pump } from './uploadQueue';
import { useQueue } from './useQueue';
import { SermonList } from './pages/SermonList';
import { RecordPage } from './pages/RecordPage';
import { SermonPage } from './pages/SermonPage';
import './styles.css';


// ---------------------------------------------------------------- login

function Login({ onDone }: { onDone: () => void }) {
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
        <p className="muted">Sign in with the Sermon Intelligence password.</p>
        <form onSubmit={submit}>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error && <p className="alert error">{error}</p>}
          <button className="btn btn-primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  );
}

// ---------------------------------------------------------------- shell

function App() {
  const path = usePath();
  const queue = useQueue();
  const [token, setToken] = useState(auth.get());
  useEffect(() => {
    const onAuth = () => setToken(auth.get());
    window.addEventListener('sermon-auth', onAuth);
    return () => window.removeEventListener('sermon-auth', onAuth);
  }, []);

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
            <a className="ghost-link" href={PORTAL}>← CMGI Apps</a>
            {token && <button className="ghost-link" onClick={() => { auth.clear(); setToken(''); }}>Sign out</button>}
          </div>
        </div>
      </header>
      {queue?.error && <div className="container"><p className="alert error">{queue.error}</p></div>}
      {token ? page : <Login onDone={() => setToken(auth.get())} />}
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
