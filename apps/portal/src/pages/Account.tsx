import { useEffect, useState, type FormEvent } from 'react';
import { api, IN_APP, daysLeft, formatDate, minutes, refreshAccount, setAccount, signOut, useAccount, type Account as AccountT } from '../account';
import { Icon } from '../components/Icon';
import { t, tError } from '../i18n';
import type { Key } from '../i18n/en';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

function planText(a: AccountT) {
  if (!a.pro) return t(a.trial_used ? 'account.plan.trialEnded' : 'account.plan.confirm');
  const date = formatDate(a.pro_until);
  if (a.pro_source === 'trial') {
    const days = daysLeft(a.pro_until);
    return days === 1 ? t('account.plan.trialOne', { date }) : t('account.plan.trialMany', { days, date });
  }
  if (a.pro_source === 'subscription') return t('account.plan.subscription', { date });
  return a.pro_until ? t('account.plan.grantUntil', { date }) : t('account.plan.grantForever');
}

const INCLUDED: { app: string; free: Key; pro: Key }[] = [
  { app: 'EventPass', free: 'account.inc.eventpass.free', pro: 'account.inc.eventpass.pro' },
  { app: 'Body of Christ', free: 'account.inc.boc.free', pro: 'account.inc.boc.pro' },
  { app: 'Sermon Intelligence', free: 'account.inc.sermon.free', pro: 'account.inc.sermon.pro' },
];

export function Account() {
  const { account, loading } = useAccount();
  const params = new URLSearchParams(window.location.search);
  const verify = params.get('verify');
  const paid = params.get('paid');
  if (loading) return <PageHead eyebrow={t('account.eyebrow')} title={t('account.loading')} />;
  if (!account) { navigate('/login?next=/account'); return null; }
  return (
    <>
      <PageHead eyebrow={t('account.eyebrow')} title={account.name} text={account.email} />
      <section className="section section-tight">
        <div className="container account-grid">
          {verify === 'ok' && <p className="banner banner-ok">{t('account.verifyOk')}</p>}
          {verify === 'invalid' && <p className="banner banner-warn">{t('account.verifyInvalid')}</p>}
          {!account.email_verified && <VerifyBanner />}
          {paid && <PaidBanner kind={paid} />}

          <article className={`plan-card ${account.pro ? 'is-pro' : ''}`}>
            <div className="plan-top">
              <span className={`plan-badge ${account.pro ? 'pro' : 'free'}`}>{account.pro ? 'PRO' : 'FREE'}</span>
              {account.pro_source === 'trial' && <span className="status-pill status-coming-soon">{t('account.trial')}</span>}
            </div>
            <h2>{account.pro ? 'CMGI Pro' : 'CMGI Free'}</h2>
            <p>{planText(account)}</p>
            {!IN_APP && account.pro_source !== 'subscription' && account.pro_source !== 'grant' && (
              <Link to="/pricing" className="btn btn-primary">{account.pro ? t('account.keepPro') : t('account.upgrade')} <Icon name="arrow" size={18} /></Link>
            )}
            {!IN_APP && account.subscription && <ManageButton />}
          </article>

          <article className="plan-card">
            <div className="plan-top"><span className="app-icon"><Icon name="waveform" /></span></div>
            <h2>{minutes(account.ai_credit_seconds)}</h2>
            <p>{t('account.aiCredit')}</p>
            {!IN_APP && <Link to="/pricing" className="btn btn-ghost">{t('account.buyMinutes')}</Link>}
          </article>

          <article className="panel-card wide">
            <h3>{t('account.included')}</h3>
            <div className="included">
              {INCLUDED.map((row) => (
                <div key={row.app} className="included-row">
                  <strong>{row.app}</strong>
                  <span><b>{t('account.free')}</b> {t(row.free)}</span>
                  <span className={account.pro ? 'on' : 'off'}><b>{t('account.pro')}</b> {t(row.pro)}</span>
                </div>
              ))}
            </div>
            <div className="auth-actions">
              <a className="btn btn-ghost btn-small" href="/eventpass/">EventPass</a>
              <a className="btn btn-ghost btn-small" href="/sermon-ai/">Sermon Intelligence</a>
              <a className="btn btn-ghost btn-small" href="/bodyofchrist/">Body of Christ</a>
              {account.is_admin && <Link to="/admin" className="btn btn-primary btn-small"><Icon name="shield" size={16} /> {t('account.adminConsole')}</Link>}
            </div>
          </article>

          <ProfileCard account={account} />
          {account.has_password ? <PasswordCard /> : (
            <article className="panel-card"><h3>{t('account.changePassword')}</h3><p className="hint">{t('account.googleOnly')}</p></article>
          )}

          <div className="wide auth-actions">
            <button className="btn btn-ghost" onClick={async () => { await signOut(); navigate('/'); }}>{t('account.signOut')}</button>
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
    catch (err) { setError(tError((err as Error).message)); }
  }
  return <>{' '}<button className="btn btn-ghost" onClick={open}>{t('account.manage')}</button>{error && <p className="hint">{error}</p>}</>;
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
    ? (done ? t('account.paidProDone') : t('account.paidProWait'))
    : t('account.paidMinutes')}</p>;
}

function VerifyBanner() {
  const [state, setState] = useState<'idle' | 'sent' | 'error'>('idle');
  return (
    <p className="banner banner-warn">
      {t('account.verifyPending')}{' '}
      {state === 'idle' && <button className="link-button" onClick={() => api('/resend-verification', { method: 'POST' }).then(() => setState('sent'), () => setState('error'))}>{t('account.resend')}</button>}
      {state === 'sent' && <b>{t('account.resent')}</b>}
      {state === 'error' && <b>{t('account.resendWait')}</b>}
    </p>
  );
}

function ProfileCard({ account }: { account: AccountT }) {
  const [name, setName] = useState(account.name);
  const [msg, setMsg] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault();
    try { setAccount(await api<AccountT>('/me', { method: 'PATCH', body: { name } })); setMsg(t('account.saved')); }
    catch (err) { setMsg(tError((err as Error).message)); }
  }
  return (
    <form className="panel-card" onSubmit={save}>
      <h3>{t('account.profile')}</h3>
      <label className="field">{t('auth.name')}<input required minLength={2} maxLength={120} value={name} onChange={(e) => { setName(e.target.value); setMsg(''); }} /></label>
      <label className="field">{t('auth.email')}<input value={account.email} disabled /></label>
      <div className="auth-actions"><button className="btn btn-primary btn-small">{t('account.save')}</button>{msg && <span className="hint">{msg}</span>}</div>
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
      setForm({ current_password: '', new_password: '' }); setMsg(t('account.passwordChanged'));
      refreshAccount();
    } catch (err) { setMsg(tError((err as Error).message)); }
  }
  return (
    <form className="panel-card" onSubmit={save}>
      <h3>{t('account.changePassword')}</h3>
      <label className="field">{t('account.currentPassword')}<input required type="password" autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} /></label>
      <label className="field">{t('reset.new')}<input required type="password" minLength={8} autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></label>
      <div className="auth-actions"><button className="btn btn-primary btn-small">{t('account.changePassword')}</button>{msg && <span className="hint">{msg}</span>}</div>
    </form>
  );
}
