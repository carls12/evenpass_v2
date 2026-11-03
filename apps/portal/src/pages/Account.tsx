import { useEffect, useState, type FormEvent } from 'react';
import { api, daysLeft, formatDate, minutes, refreshAccount, setAccount, signOut, useAccount, type Account as AccountT } from '../account';
import { Icon } from '../components/Icon';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

function planText(a: AccountT) {
  if (!a.pro) return a.trial_used ? 'Your free trial has ended.' : 'Confirm your email address to start the free 14-day Pro trial.';
  if (a.pro_source === 'trial') return `Free trial — ${daysLeft(a.pro_until)} day${daysLeft(a.pro_until) === 1 ? '' : 's'} left (until ${formatDate(a.pro_until)}).`;
  if (a.pro_source === 'subscription') return `Pro subscription — renews ${formatDate(a.pro_until)}.`;
  return a.pro_until ? `Pro given by CMGI until ${formatDate(a.pro_until)}.` : 'Pro given by CMGI, without end date.';
}

const INCLUDED: { app: string; free: string; pro: string }[] = [
  { app: 'EventPass', free: 'Create events, online registration, participant list', pro: 'Badge design & printing, QR check-in at the gate, gate staff access' },
  { app: 'Body of Christ', free: 'Bible reading, personal goals, view your progress', pro: 'Everything, incl. reports, printing, assemblies and chat' },
  { app: 'Sermon Intelligence', free: 'Recordings, transcripts with your AI credit', pro: 'Uses your AI credit (bought separately)' },
];

export function Account() {
  const { account, loading } = useAccount();
  const params = new URLSearchParams(window.location.search);
  const verify = params.get('verify');
  const paid = params.get('paid');
  if (loading) return <PageHead eyebrow="Account" title="Loading …" />;
  if (!account) { navigate('/login?next=/account'); return null; }
  return (
    <>
      <PageHead eyebrow="My account" title={account.name} text={account.email} />
      <section className="section section-tight">
        <div className="container account-grid">
          {verify === 'ok' && <p className="banner banner-ok">✓ Your email address is confirmed — enjoy your free Pro trial.</p>}
          {verify === 'invalid' && <p className="banner banner-warn">This confirmation link is invalid or has expired. Request a new one below.</p>}
          {!account.email_verified && <VerifyBanner />}
          {paid && <PaidBanner kind={paid} />}

          <article className={`plan-card ${account.pro ? 'is-pro' : ''}`}>
            <div className="plan-top">
              <span className={`plan-badge ${account.pro ? 'pro' : 'free'}`}>{account.pro ? 'PRO' : 'FREE'}</span>
              {account.pro_source === 'trial' && <span className="status-pill status-coming-soon">Trial</span>}
            </div>
            <h2>{account.pro ? 'CMGI Pro' : 'CMGI Free'}</h2>
            <p>{planText(account)}</p>
            {account.pro_source !== 'subscription' && account.pro_source !== 'grant' && (
              <Link to="/pricing" className="btn btn-primary">{account.pro ? 'Keep Pro after the trial' : 'Upgrade to Pro'} <Icon name="arrow" size={18} /></Link>
            )}
            {account.subscription && <ManageButton />}
          </article>

          <article className="plan-card">
            <div className="plan-top"><span className="app-icon"><Icon name="waveform" /></span></div>
            <h2>{minutes(account.ai_credit_seconds)}</h2>
            <p>AI transcription credit for Sermon Intelligence.</p>
            <Link to="/pricing" className="btn btn-ghost">Buy more minutes</Link>
          </article>

          <article className="panel-card wide">
            <h3>What your plan includes</h3>
            <div className="included">
              {INCLUDED.map((row) => (
                <div key={row.app} className="included-row">
                  <strong>{row.app}</strong>
                  <span><b>Free:</b> {row.free}</span>
                  <span className={account.pro ? 'on' : 'off'}><b>Pro:</b> {row.pro}</span>
                </div>
              ))}
            </div>
            <div className="auth-actions">
              <a className="btn btn-ghost btn-small" href="/eventpass/">EventPass</a>
              <a className="btn btn-ghost btn-small" href="/sermon-ai/">Sermon Intelligence</a>
              <a className="btn btn-ghost btn-small" href="/bodyofchrist/">Body of Christ</a>
              {account.is_admin && <Link to="/admin" className="btn btn-primary btn-small"><Icon name="shield" size={16} /> Admin console</Link>}
            </div>
          </article>

          <ProfileCard account={account} />
          <PasswordCard />

          <div className="wide auth-actions">
            <button className="btn btn-ghost" onClick={async () => { await signOut(); navigate('/'); }}>Sign out</button>
          </div>
        </div>
      </section>
    </>
  );
}

function ManageButton() {
  const [error, setError] = useState('');
  async function open() {
    try { window.location.assign((await api<{ url: string }>('/billing/portal', { method: 'POST' })).url); }
    catch (err) { setError((err as Error).message); }
  }
  return <>{' '}<button className="btn btn-ghost" onClick={open}>Manage subscription & invoices</button>{error && <p className="hint">{error}</p>}</>;
}

/** Stripe confirms payments a few seconds later via its webhook: refresh until the account shows it. */
function PaidBanner({ kind }: { kind: string }) {
  const { account } = useAccount();
  const done = kind === 'pro' ? account?.pro_source === 'subscription' : true;
  useEffect(() => {
    if (done) return;
    const timer = window.setInterval(refreshAccount, 3000);
    return () => window.clearInterval(timer);
  }, [done]);
  return <p className="banner banner-ok">{kind === 'pro'
    ? (done ? '✓ Thank you! CMGI Pro is active for all apps.' : 'Thank you! Your payment is being confirmed — Pro switches on in a few seconds …')
    : '✓ Thank you! Your AI minutes are added as soon as the payment is confirmed.'}</p>;
}

function VerifyBanner() {
  const [state, setState] = useState<'idle' | 'sent' | 'error'>('idle');
  return (
    <p className="banner banner-warn">
      Please confirm your email address — we sent you a link. Your free trial starts once it is confirmed.{' '}
      {state === 'idle' && <button className="link-button" onClick={() => api('/resend-verification', { method: 'POST' }).then(() => setState('sent'), () => setState('error'))}>Send the link again</button>}
      {state === 'sent' && <b>Sent — check your inbox and spam folder.</b>}
      {state === 'error' && <b>Please wait a few minutes before trying again.</b>}
    </p>
  );
}

function ProfileCard({ account }: { account: AccountT }) {
  const [name, setName] = useState(account.name);
  const [msg, setMsg] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault();
    try { setAccount(await api<AccountT>('/me', { method: 'PATCH', body: { name } })); setMsg('Saved ✓'); }
    catch (err) { setMsg((err as Error).message); }
  }
  return (
    <form className="panel-card" onSubmit={save}>
      <h3>Profile</h3>
      <label className="field">Full name<input required minLength={2} maxLength={120} value={name} onChange={(e) => { setName(e.target.value); setMsg(''); }} /></label>
      <label className="field">Email<input value={account.email} disabled /></label>
      <div className="auth-actions"><button className="btn btn-primary btn-small">Save</button>{msg && <span className="hint">{msg}</span>}</div>
    </form>
  );
}

function PasswordCard() {
  const [form, setForm] = useState({ current_password: '', new_password: '' });
  const [msg, setMsg] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api('/me/password', { method: 'POST', body: form });
      setForm({ current_password: '', new_password: '' }); setMsg('Password changed ✓ — other devices were signed out.');
      refreshAccount();
    } catch (err) { setMsg((err as Error).message); }
  }
  return (
    <form className="panel-card" onSubmit={save}>
      <h3>Change password</h3>
      <label className="field">Current password<input required type="password" autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} /></label>
      <label className="field">New password<input required type="password" minLength={8} autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></label>
      <div className="auth-actions"><button className="btn btn-primary btn-small">Change password</button>{msg && <span className="hint">{msg}</span>}</div>
    </form>
  );
}
