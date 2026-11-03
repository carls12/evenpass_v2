import { useEffect, useState, type FormEvent } from 'react';
import { api, daysLeft, formatDate, minutes, useAccount, type Account } from '../account';
import { Icon } from '../components/Icon';
import { navigate } from '../router';
import { PageHead } from './PageHead';

interface AdminUser extends Account { disabled: boolean; last_login_at: string | null }
interface Detail extends AdminUser {
  grants: { id: number; until: string | null; note: string; granted_by: string; created_at: string; revoked_at: string | null }[];
  credits: { seconds: number; reason: string; note: string; created_by: string; created_at: string }[];
}
interface Overview { users: number; new_7_days: number; pro: number; pro_trial: number; pro_paid: number; pro_granted: number; mail_enabled: boolean }

function planLabel(u: Account) {
  if (!u.pro) return <span className="plan-badge free">FREE</span>;
  const label = { trial: `Trial · ${daysLeft(u.pro_until)} d`, subscription: 'Paid', grant: u.pro_until ? `Given · until ${formatDate(u.pro_until)}` : 'Given · no end' }[u.pro_source!];
  return <><span className="plan-badge pro">PRO</span> <small>{label}</small></>;
}

export function Admin() {
  const { account, loading } = useAccount();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState('');

  async function load(query = q) {
    try {
      const [o, list] = await Promise.all([api<Overview>('/admin/overview'), api<AdminUser[]>(`/admin/users?q=${encodeURIComponent(query)}`)]);
      setOverview(o); setUsers(list); setError('');
    } catch (err) { setError((err as Error).message); }
  }
  useEffect(() => { if (account?.is_admin) load(''); }, [account?.is_admin]);
  useEffect(() => { if (!account?.is_admin) return; const t = setTimeout(() => load(q), 250); return () => clearTimeout(t); }, [q]);

  if (loading) return <PageHead eyebrow="Admin" title="Loading …" />;
  if (!account) { navigate('/login?next=/admin'); return null; }
  if (!account.is_admin) return <PageHead eyebrow="Admin" title="No access" text="The admin console is only for CMGI platform admins." />;

  return (
    <>
      <PageHead eyebrow="Admin console" title="Users & Pro access" text="Give people Pro, add AI minutes, help with passwords." />
      <section className="section section-tight">
        <div className="container">
          {overview && (
            <div className="metric-row">
              <div className="metric"><strong>{overview.users}</strong><span>Accounts</span><small>+{overview.new_7_days} this week</small></div>
              <div className="metric"><strong>{overview.pro}</strong><span>Pro now</span><small>{overview.pro_paid} paid · {overview.pro_granted} given · {overview.pro_trial} trial</small></div>
              <div className="metric"><strong>{overview.mail_enabled ? 'On' : 'Off'}</strong><span>Email sending</span><small>{overview.mail_enabled ? 'Confirmation & reset mails' : 'Accounts confirm instantly'}</small></div>
            </div>
          )}
          {error && <p className="banner banner-warn">{error}</p>}
          <div className="admin-layout">
            <div className="panel-card">
              <label className="field search"><span className="sr-only">Search</span>
                <input placeholder="Search by name or email …" value={q} onChange={(e) => setQ(e.target.value)} />
              </label>
              <div className="table-wrap">
                <table className="admin-table">
                  <thead><tr><th>Name</th><th>Plan</th><th>AI credit</th><th>Joined</th></tr></thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className={`${selected === u.id ? 'selected' : ''} ${u.disabled ? 'is-disabled' : ''}`} onClick={() => setSelected(u.id)}>
                        <td><strong>{u.name}</strong>{u.is_admin && <span className="tag">admin</span>}{u.disabled && <span className="tag warn">deactivated</span>}<br /><small>{u.email}</small></td>
                        <td>{planLabel(u)}</td>
                        <td>{minutes(u.ai_credit_seconds)}</td>
                        <td><small>{formatDate(u.created_at)}</small></td>
                      </tr>
                    ))}
                    {!users.length && <tr><td colSpan={4} className="empty">No accounts found.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {selected ? <UserPanel id={selected} onChange={() => load()} /> : (
              <aside className="panel-card admin-hint"><Icon name="shield" /><p>Choose a person to give Pro, add AI minutes or create a password reset link.</p></aside>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

const PRESETS = [{ label: '1 month', days: 30 }, { label: '3 months', days: 91 }, { label: '1 year', days: 365 }, { label: 'No end date', days: 0 }];

function UserPanel({ id, onChange }: { id: string; onChange: () => void }) {
  const [u, setU] = useState<Detail | null>(null);
  const [days, setDays] = useState(30);
  const [note, setNote] = useState('');
  const [credit, setCredit] = useState({ minutes: 60, note: '' });
  const [msg, setMsg] = useState('');
  const [link, setLink] = useState('');

  async function load() { setU(await api<Detail>(`/admin/users/${id}`)); }
  useEffect(() => { setU(null); setMsg(''); setLink(''); load().catch((e) => setMsg(e.message)); }, [id]);
  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); await load(); onChange(); setMsg(ok); } catch (err) { setMsg((err as Error).message); }
  }
  if (!u) return <aside className="panel-card">Loading …</aside>;

  const grant = (e: FormEvent) => {
    e.preventDefault();
    const until = days ? new Date(Date.now() + days * 86_400_000).toISOString() : null;
    act(() => api(`/admin/users/${id}/pro`, { method: 'POST', body: { until, note } }), 'Pro given ✓');
  };
  const activeGrants = u.grants.filter((g) => !g.revoked_at && (!g.until || new Date(g.until) > new Date()));

  return (
    <aside className="panel-card user-panel">
      <h3>{u.name}</h3>
      <p className="muted-line">{u.email} · joined {formatDate(u.created_at)} · last sign-in {formatDate(u.last_login_at)}</p>
      <div className="user-plan">{planLabel(u)} {!u.email_verified && <span className="tag warn">email not confirmed</span>}</div>

      <form onSubmit={grant} className="admin-block">
        <h4>Give Pro</h4>
        <div className="chip-row">
          {PRESETS.map((p) => (
            <button type="button" key={p.label} className={`chip ${days === p.days ? 'active' : ''}`} onClick={() => setDays(p.days)}>{p.label}</button>
          ))}
        </div>
        <label className="field">Note (optional)<input maxLength={300} placeholder="e.g. Pastor, ministry partner" value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <div className="auth-actions">
          <button className="btn btn-primary btn-small">Give Pro</button>
          {activeGrants.length > 0 && (
            <button type="button" className="btn btn-ghost btn-small" onClick={() => act(() => api(`/admin/users/${id}/pro`, { method: 'DELETE' }), 'Given Pro ended')}>End given Pro</button>
          )}
        </div>
      </form>

      <form className="admin-block" onSubmit={(e) => { e.preventDefault(); act(() => api(`/admin/users/${id}/credits`, { method: 'POST', body: credit }), 'AI minutes updated ✓'); }}>
        <h4>AI minutes <small>(now {minutes(u.ai_credit_seconds)})</small></h4>
        <div className="two-col">
          <label className="field">Minutes (negative removes)<input type="number" min={-6000} max={6000} required value={credit.minutes} onChange={(e) => setCredit({ ...credit, minutes: Number(e.target.value) })} /></label>
          <label className="field">Note<input maxLength={300} value={credit.note} onChange={(e) => setCredit({ ...credit, note: e.target.value })} /></label>
        </div>
        <button className="btn btn-ghost btn-small">Book minutes</button>
      </form>

      <div className="admin-block">
        <h4>Help & access</h4>
        <div className="auth-actions">
          <button className="btn btn-ghost btn-small" onClick={() => act(async () => setLink((await api<{ link: string }>(`/admin/users/${id}/reset-link`, { method: 'POST' })).link), 'Reset link created (valid 24 h)')}>Create password reset link</button>
          <button className="btn btn-ghost btn-small" onClick={() => { if (u.disabled || confirm(`Deactivate ${u.name}? They are signed out everywhere.`)) act(() => api(`/admin/users/${id}/disable`, { method: 'POST', body: { disabled: !u.disabled } }), u.disabled ? 'Account active again' : 'Account deactivated'); }}>
            {u.disabled ? 'Reactivate account' : 'Deactivate account'}
          </button>
        </div>
        {link && <textarea className="copy-box" readOnly rows={3} value={link} onFocus={(e) => e.target.select()} />}
      </div>
      {msg && <p className="hint" role="status">{msg}</p>}

      <div className="admin-block">
        <h4>History</h4>
        <ul className="history">
          {u.grants.map((g) => <li key={`g${g.id}`}><b>Pro</b> {g.until ? `until ${formatDate(g.until)}` : 'no end date'} · {g.granted_by}{g.note && ` · ${g.note}`}{g.revoked_at && ' · ended'} <small>{formatDate(g.created_at)}</small></li>)}
          {u.credits.map((c, i) => <li key={`c${i}`}><b>{c.seconds > 0 ? '+' : '−'}{minutes(Math.abs(c.seconds))}</b> {c.reason}{c.note && ` · ${c.note}`} <small>{formatDate(c.created_at)}</small></li>)}
          {!u.grants.length && !u.credits.length && <li className="empty">Nothing yet.</li>}
        </ul>
      </div>
    </aside>
  );
}
