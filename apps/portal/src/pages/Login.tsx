import { useEffect, useState, type FormEvent } from 'react';
import { api, IN_APP, nextPath, setAccount, useAccount, type Account } from '../account';
import { Icon } from '../components/Icon';
import { t, tError, tx } from '../i18n';
import type { Key } from '../i18n/en';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

type Mode = 'signin' | 'register';

/** Continues to the page the user came from; other apps (/eventpass/ …) are full page loads. */
function goNext() {
  const next = nextPath();
  const portalPage = ['/account', '/admin', '/apps', '/'].includes(next);
  if (portalPage) navigate(next); else window.location.assign(next);
}

const GOOGLE_ERRORS = ['google', 'google_cancelled', 'google_unverified', 'disabled'];

/** Shown only when the server has a Google client configured. Google refuses sign-in inside app web views. */
function GoogleButton() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => { api<{ google: boolean }>('/providers').then((p) => setEnabled(p.google), () => undefined); }, []);
  if (!enabled) return null;
  if (IN_APP) return <p className="hint auth-or-note">{t('auth.googleInApp')}</p>;
  return (
    <>
      <div className="auth-or"><span>{t('auth.or')}</span></div>
      <a className="btn btn-google auth-submit" href={`/api/accounts/google/start?next=${encodeURIComponent(nextPath())}`}>
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.8 6C12.4 13.6 17.7 9.5 24 9.5z" />
          <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
          <path fill="#FBBC05" d="M10.5 28.7c-.5-1.4-.8-3-.8-4.7s.3-3.3.8-4.7l-7.8-6C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.8-6z" />
          <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.8 6C6.6 42.6 14.6 48 24 48z" />
        </svg>
        {t('auth.google')}
      </a>
    </>
  );
}

export function Login({ initialMode = 'signin' }: { initialMode?: Mode }) {
  const { account } = useAccount();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const urlError = new URLSearchParams(window.location.search).get('error') || '';
  const [error, setError] = useState(GOOGLE_ERRORS.includes(urlError) ? t(`auth.error.${urlError}` as Key) : '');
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
      setError(tError((err as Error).message));
    } finally { setBusy(false); }
  }

  if (account) {
    return (
      <>
        <PageHead eyebrow={t('auth.eyebrow')} title={t('auth.welcome', { name: account.name.split(' ')[0] })} text={t('auth.signedInEverywhere')} />
        <section className="section section-tight"><div className="container auth-actions">
          <Link to="/account" className="btn btn-primary">{t('auth.myAccount')} <Icon name="arrow" size={18} /></Link>
          <Link to="/apps" className="btn btn-ghost">{t('auth.openApp')}</Link>
        </div></section>
      </>
    );
  }

  const register = mode === 'register';
  return (
    <>
      <PageHead eyebrow={t('auth.eyebrow')} title={register ? t('auth.registerTitle') : t('auth.signInTitle')} text={t('auth.intro')} />
      <section className="section section-tight">
        <div className="container auth-layout">
          <form className="auth-card reveal" onSubmit={submit}>
            <div className="auth-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={!register} className={!register ? 'active' : ''} onClick={() => { setMode('signin'); setError(''); }}>{t('auth.tabSignIn')}</button>
              <button type="button" role="tab" aria-selected={register} className={register ? 'active' : ''} onClick={() => { setMode('register'); setError(''); }}>{t('auth.tabRegister')}</button>
            </div>
            {register && (
              <label className="field">{t('auth.name')}
                <input required minLength={2} maxLength={120} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
            )}
            <label className="field">{t('auth.email')}
              <input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>
            <label className="field">{t('auth.password')}
              <input required type="password" minLength={register ? 8 : undefined} autoComplete={register ? 'new-password' : 'current-password'}
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              {register && <small>{t('auth.min8')}</small>}
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit" disabled={busy}>
              {busy ? t('auth.wait') : register ? t('auth.submitRegister') : t('auth.submitSignIn')}
            </button>
            {!register && <Link to="/forgot-password" className="auth-link">{t('auth.forgotLink')}</Link>}
            <GoogleButton />
          </form>
          <aside className="auth-aside reveal">
            <h3>{register ? t('auth.asideTrial') : t('auth.asideOne')}</h3>
            <ul className="app-highlights">
              <li>{t('auth.a1')}</li>
              <li>{t('auth.a2')}</li>
              <li>{t('auth.a3')}</li>
              <li>{register ? t('auth.a4Register') : t('auth.a4SignIn')}</li>
            </ul>
            <p className="note"><Icon name="scan" size={16} /> {tx('auth.gateNote', { link: <a href="/eventpass/gate">{t('auth.gateLink')}</a> })}</p>
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
    catch (err) { setError(tError((err as Error).message)); }
  }
  return (
    <>
      <PageHead eyebrow={t('auth.eyebrow')} title={t('forgot.title')} text={t('forgot.text')} />
      <section className="section section-tight"><div className="container auth-layout single">
        <form className="auth-card" onSubmit={submit}>
          {sent === null ? <>
            <label className="field">{t('auth.email')}<input required type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit">{t('forgot.send')}</button>
          </> : sent ? (
            <p className="form-ok">{tx('forgot.sent', { email: <b>{email}</b> })}</p>
          ) : (
            <p className="form-ok">{t('forgot.noMail')}</p>
          )}
          <Link to="/login" className="auth-link">{t('forgot.back')}</Link>
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
    catch (err) { setError(tError((err as Error).message)); }
  }
  return (
    <>
      <PageHead eyebrow={t('auth.eyebrow')} title={t('reset.title')} />
      <section className="section section-tight"><div className="container auth-layout single">
        <form className="auth-card" onSubmit={submit}>
          {done ? <>
            <p className="form-ok">{t('reset.done')}</p>
            <Link to="/login" className="btn btn-primary auth-submit">{t('auth.submitSignIn')}</Link>
          </> : <>
            <label className="field">{t('reset.new')}
              <input required type="password" minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <small>{t('auth.min8')}</small>
            </label>
            {!token && <p className="form-error">{t('reset.incomplete')}</p>}
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn btn-primary auth-submit" disabled={!token}>{t('reset.save')}</button>
          </>}
        </form>
      </div></section>
    </>
  );
}
