import { useState, type FormEvent } from 'react';
import { api, nextPath, setAccount, useAccount, type Account } from '../account';
import { Icon } from '../components/Icon';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

type Mode = 'signin' | 'register';

/** Continues to the page the user came from; other apps (/eventpass/ …) are full page loads. */
function goNext() {
  const next = nextPath();
  const portalPage = ['/account', '/admin', '/apps', '/'].includes(next);
  if (portalPage) navigate(next); else window.location.assign(next);
}

export function Login({ initialMode = 'signin' }: { initialMode?: Mode }) {
  const { account } = useAccount();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const body = mode === 'register' ? form : { email: form.email, password: form.password };
      const res = await api<{ user: Account }>(mode === 'register' ? '/register' : '/login', { method: 'POST', body });
      setAccount(res.user);
      goNext();
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); }
  }

  if (account) {
    return (
      <>
        <PageHead eyebrow="Account" title={`Welcome, ${account.name.split(' ')[0]}`} text="You are signed in to all CMGI apps." />
        <section className="section section-tight"><div className="container auth-actions">
          <Link to="/account" className="btn btn-primary">My account <Icon name="arrow" size={18} /></Link>
          <Link to="/apps" className="btn btn-ghost">Open an app</Link>
        </div></section>
      </>
    );
  }

  const register = mode === 'register';
  return (
    <>
      <PageHead eyebrow="CMGI Account" title={register ? 'Create your account' : 'Sign in'}
        text="One account for EventPass, Sermon Intelligence, Body of Christ and every future CMGI app." />
      <section className="section section-tight">
        <div className="container auth-layout">
          <form className="auth-card reveal" onSubmit={submit}>
            <div className="auth-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={!register} className={!register ? 'active' : ''} onClick={() => { setMode('signin'); setError(''); }}>Sign in</button>
              <button type="button" role="tab" aria-selected={register} className={register ? 'active' : ''} onClick={() => { setMode('register'); setError(''); }}>Create account</button>
            </div>
            {register && (
              <label className="field">Full name
                <input required minLength={2} maxLength={120} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
            )}
            <label className="field">Email
              <input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>
            <label className="field">Password
              <input required type="password" minLength={register ? 8 : undefined} autoComplete={register ? 'new-password' : 'current-password'}
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              {register && <small>At least 8 characters.</small>}
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit" disabled={busy}>
              {busy ? 'Please wait …' : register ? 'Create account & start free trial' : 'Sign in'}
            </button>
            {!register && <Link to="/forgot-password" className="auth-link">Forgot your password?</Link>}
          </form>
          <aside className="auth-aside reveal">
            <h3>{register ? 'Your free 14-day Pro trial' : 'One login, every app'}</h3>
            <ul className="app-highlights">
              <li>EventPass: create events for free; badges and gate check-in with Pro</li>
              <li>Sermon Intelligence: 5 free minutes of transcription to try it</li>
              <li>Body of Christ: all features during the trial, then reports with Pro</li>
              <li>{register ? 'No payment details needed for the trial' : 'Signed in here means signed in everywhere'}</li>
            </ul>
            <p className="note"><Icon name="scan" size={16} /> Gate staff for an event sign in with their temporary access: <a href="/eventpass/gate">gate sign-in</a>.</p>
          </aside>
        </div>
      </section>
    </>
  );
}

export function Register() { return <Login initialMode="register" />; }

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState<null | boolean>(null);
  const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault(); setError('');
    try { setSent((await api<{ mail: boolean }>('/password/forgot', { method: 'POST', body: { email } })).mail); }
    catch (err) { setError((err as Error).message); }
  }
  return (
    <>
      <PageHead eyebrow="CMGI Account" title="Forgot your password?" text="We will send you a link to choose a new one." />
      <section className="section section-tight"><div className="container auth-layout single">
        <form className="auth-card" onSubmit={submit}>
          {sent === null ? <>
            <label className="field">Email<input required type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit">Send reset link</button>
          </> : sent ? (
            <p className="form-ok">If an account exists for <b>{email}</b>, a link is on its way. Please also check your spam folder.</p>
          ) : (
            <p className="form-ok">Email is not set up on this server yet. Please ask the CMGI admin for a reset link.</p>
          )}
          <Link to="/login" className="auth-link">Back to sign in</Link>
        </form>
      </div></section>
    </>
  );
}

export function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get('token') || '';
  const [password, setPassword] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault(); setError('');
    try { await api('/password/reset', { method: 'POST', body: { token, password } }); setDone(true); }
    catch (err) { setError((err as Error).message); }
  }
  return (
    <>
      <PageHead eyebrow="CMGI Account" title="Choose a new password" />
      <section className="section section-tight"><div className="container auth-layout single">
        <form className="auth-card" onSubmit={submit}>
          {done ? <>
            <p className="form-ok">Your password has been changed. You can sign in now.</p>
            <Link to="/login" className="btn btn-primary auth-submit">Sign in</Link>
          </> : <>
            <label className="field">New password
              <input required type="password" minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <small>At least 8 characters.</small>
            </label>
            {!token && <p className="form-error">This link is incomplete. Please open the link from the email again.</p>}
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit" disabled={!token}>Save new password</button>
          </>}
        </form>
      </div></section>
    </>
  );
}
