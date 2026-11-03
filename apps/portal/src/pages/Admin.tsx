import { useEffect, useState, type FormEvent } from 'react';
import { api, daysLeft, formatDate, minutes, useAccount, type Account } from '../account';
import { Icon } from '../components/Icon';
import { t, tError } from '../i18n';
import type { Key } from '../i18n/en';
import { navigate } from '../router';
import { PageHead } from './PageHead';
import { AdminOrgs } from './AdminOrgs';

interface AdminUser extends Account { disabled: boolean; last_login_at: string | null }
interface Detail extends AdminUser {
  grants: { id: number; until: string | null; note: string; granted_by: string; created_at: string; revoked_at: string | null }[];
  credits: { seconds: number; reason: string; note: string; created_by: string; created_at: string }[];
}
interface Overview { users: number; new_7_days: number; pro: number; pro_trial: number; pro_paid: number; pro_granted: number; mail_enabled: boolean }

function planLabel(u: Account) {
  if (!u.pro) return <span className="plan-badge free">FREE</span>;
  const label = {
    trial: t('admin.planTrial', { days: daysLeft(u.pro_until) }),
    subscription: t('admin.planPaid'),
    grant: u.pro_until ? t('admin.planGivenUntil', { date: formatDate(u.pro_until) }) : t('admin.planGivenForever'),
    organisation: t('admin.planOrg'),
  }[u.pro_source!];
  return <><span className="plan-badge pro">PRO</span> <small>{label}</small></>;
}

export function Admin() {
  const { account, loading } = useAccount();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'users' | 'orgs'>(window.location.hash === '#orgs' ? 'orgs' : 'users');

  async function load(query = q) {
    try {
      const [o, list] = await Promise.all([api<Overview>('/admin/overview'), api<AdminUser[]>(`/admin/users?q=${encodeURIComponent(query)}`)]);
      setOverview(o); setUsers(list); setError('');
    } catch (err) { setError(tError((err as Error).message)); }
  }
  useEffect(() => { if (account?.is_admin) load(''); }, [account?.is_admin]);
  useEffect(() => { if (!account?.is_admin) return; const timer = setTimeout(() => load(q), 250); return () => clearTimeout(timer); }, [q]);

  if (loading) return <PageHead eyebrow={t('admin.eyebrow')} title={t('account.loading')} />;
  if (!account) { navigate('/login?next=/admin'); return null; }
  if (!account.is_admin) return <PageHead eyebrow={t('admin.eyebrow')} title={t('admin.noAccess')} text={t('admin.noAccessText')} />;

  return (
    <>
      <PageHead eyebrow={t('admin.eyebrow')} title={t('admin.title')} text={t('admin.text')} />
      <section className="section section-tight">
        <div className="container">
          <div className="filter-bar" role="tablist">
            <button role="tab" aria-selected={tab === 'users'} className={`chip ${tab === 'users' ? 'active' : ''}`} onClick={() => { setTab('users'); window.history.replaceState({}, '', '/admin'); }}>{t('admin.tabUsers')}</button>
            <button role="tab" aria-selected={tab === 'orgs'} className={`chip ${tab === 'orgs' ? 'active' : ''}`} onClick={() => { setTab('orgs'); window.history.replaceState({}, '', '/admin#orgs'); }}>{t('admin.tabOrgs')}</button>
          </div>
          {tab === 'orgs' ? <AdminOrgs /> : <>
          {overview && (
            <div className="metric-row">
              <div className="metric"><strong>{overview.users}</strong><span>{t('admin.accounts')}</span><small>{t('admin.thisWeek', { n: overview.new_7_days })}</small></div>
              <div className="metric"><strong>{overview.pro}</strong><span>{t('admin.proNow')}</span><small>{t('admin.proSplit', { paid: overview.pro_paid, given: overview.pro_granted, trial: overview.pro_trial })}</small></div>
              <div className="metric"><strong>{overview.mail_enabled ? t('admin.on') : t('admin.off')}</strong><span>{t('admin.mail')}</span><small>{overview.mail_enabled ? t('admin.mailOn') : t('admin.mailOff')}</small></div>
            </div>
          )}
          {error && <p className="banner banner-warn">{error}</p>}
          <div className="admin-layout">
            <div className="panel-card">
              <label className="field search"><span className="sr-only">{t('admin.search')}</span>
                <input placeholder={t('admin.search')} value={q} onChange={(e) => setQ(e.target.value)} />
              </label>
              <div className="table-wrap">
                <table className="admin-table">
                  <thead><tr><th>{t('admin.colName')}</th><th>{t('admin.colPlan')}</th><th>{t('admin.colCredit')}</th><th>{t('admin.colJoined')}</th></tr></thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className={`${selected === u.id ? 'selected' : ''} ${u.disabled ? 'is-disabled' : ''}`} onClick={() => setSelected(u.id)}>
                        <td><strong>{u.name}</strong>{u.is_admin && <span className="tag">{t('admin.tagAdmin')}</span>}{u.disabled && <span className="tag warn">{t('admin.tagDisabled')}</span>}<br /><small>{u.email}</small></td>
                        <td>{planLabel(u)}</td>
                        <td>{minutes(u.ai_credit_seconds)}</td>
                        <td><small>{formatDate(u.created_at)}</small></td>
                      </tr>
                    ))}
                    {!users.length && <tr><td colSpan={4} className="empty">{t('admin.none')}</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {selected ? <UserPanel id={selected} onChange={() => load()} /> : (
              <aside className="panel-card admin-hint"><Icon name="shield" /><p>{t('admin.hint')}</p></aside>
            )}
          </div>
          </>}
        </div>
      </section>
    </>
  );
}

const PRESETS: { label: Key; days: number }[] = [
  { label: 'admin.preset1m', days: 30 }, { label: 'admin.preset3m', days: 91 }, { label: 'admin.preset1y', days: 365 }, { label: 'admin.presetForever', days: 0 },
];

function UserPanel({ id, onChange }: { id: string; onChange: () => void }) {
  const [u, setU] = useState<Detail | null>(null);
  const [days, setDays] = useState(30);
  const [note, setNote] = useState('');
  const [credit, setCredit] = useState({ minutes: 60, note: '' });
  const [msg, setMsg] = useState('');
  const [link, setLink] = useState('');

  async function load() { setU(await api<Detail>(`/admin/users/${id}`)); }
  useEffect(() => { setU(null); setMsg(''); setLink(''); load().catch((e) => setMsg(tError(e.message))); }, [id]);
  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); await load(); onChange(); setMsg(ok); } catch (err) { setMsg(tError((err as Error).message)); }
  }
  if (!u) return <aside className="panel-card">{t('account.loading')}</aside>;

  const grant = (e: FormEvent) => {
    e.preventDefault();
    const until = days ? new Date(Date.now() + days * 86_400_000).toISOString() : null;
    act(() => api(`/admin/users/${id}/pro`, { method: 'POST', body: { until, note } }), t('admin.proGiven'));
  };
  const activeGrants = u.grants.filter((g) => !g.revoked_at && (!g.until || new Date(g.until) > new Date()));

  return (
    <aside className="panel-card user-panel">
      <h3>{u.name}</h3>
      <p className="muted-line">{t('admin.joinedLast', { email: u.email, joined: formatDate(u.created_at), last: formatDate(u.last_login_at) })}</p>
      <div className="user-plan">{planLabel(u)} {!u.email_verified && <span className="tag warn">{t('admin.unconfirmed')}</span>}</div>

      <form onSubmit={grant} className="admin-block">
        <h4>{t('admin.givePro')}</h4>
        <div className="chip-row">
          {PRESETS.map((p) => (
            <button type="button" key={p.label} className={`chip ${days === p.days ? 'active' : ''}`} onClick={() => setDays(p.days)}>{t(p.label)}</button>
          ))}
        </div>
        <label className="field">{t('admin.note')}<input maxLength={300} placeholder={t('admin.notePlaceholder')} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <div className="auth-actions">
          <button className="btn btn-primary btn-small">{t('admin.givePro')}</button>
          {activeGrants.length > 0 && (
            <button type="button" className="btn btn-ghost btn-small" onClick={() => act(() => api(`/admin/users/${id}/pro`, { method: 'DELETE' }), t('admin.proEnded'))}>{t('admin.endPro')}</button>
          )}
        </div>
      </form>

      <form className="admin-block" onSubmit={(e) => { e.preventDefault(); act(() => api(`/admin/users/${id}/credits`, { method: 'POST', body: credit }), t('admin.minutesUpdated')); }}>
        <h4>{t('pricing.minutes')} <small>{t('admin.minutesNow', { credit: minutes(u.ai_credit_seconds) })}</small></h4>
        <div className="two-col">
          <label className="field">{t('admin.minutesField')}<input type="number" min={-6000} max={6000} required value={credit.minutes} onChange={(e) => setCredit({ ...credit, minutes: Number(e.target.value) })} /></label>
          <label className="field">{t('admin.noteField')}<input maxLength={300} value={credit.note} onChange={(e) => setCredit({ ...credit, note: e.target.value })} /></label>
        </div>
        <button className="btn btn-ghost btn-small">{t('admin.bookMinutes')}</button>
      </form>

      <div className="admin-block">
        <h4>{t('admin.help')}</h4>
        <div className="auth-actions">
          <button className="btn btn-ghost btn-small" onClick={() => act(async () => setLink((await api<{ link: string }>(`/admin/users/${id}/reset-link`, { method: 'POST' })).link), t('admin.resetCreated'))}>{t('admin.resetLink')}</button>
          <button className="btn btn-ghost btn-small" onClick={() => { if (u.disabled || confirm(t('admin.confirmDeactivate', { name: u.name }))) act(() => api(`/admin/users/${id}/disable`, { method: 'POST', body: { disabled: !u.disabled } }), u.disabled ? t('admin.activeAgain') : t('admin.deactivated')); }}>
            {u.disabled ? t('admin.reactivate') : t('admin.deactivate')}
          </button>
        </div>
        {link && <textarea className="copy-box" readOnly rows={3} value={link} onFocus={(e) => e.target.select()} />}
      </div>
      {msg && <p className="hint" role="status">{msg}</p>}

      <div className="admin-block">
        <h4>{t('admin.history')}</h4>
        <ul className="history">
          {u.grants.map((g) => <li key={`g${g.id}`}><b>Pro</b> {g.until ? t('admin.histUntil', { date: formatDate(g.until) }) : t('admin.histForever')} · {g.granted_by}{g.note && ` · ${g.note}`}{g.revoked_at && t('admin.histEnded')} <small>{formatDate(g.created_at)}</small></li>)}
          {u.credits.map((c, i) => <li key={`c${i}`}><b>{c.seconds > 0 ? '+' : '−'}{minutes(Math.abs(c.seconds))}</b> {c.reason}{c.note && ` · ${c.note}`} <small>{formatDate(c.created_at)}</small></li>)}
          {!u.grants.length && !u.credits.length && <li className="empty">{t('admin.nothing')}</li>}
        </ul>
      </div>
    </aside>
  );
}
