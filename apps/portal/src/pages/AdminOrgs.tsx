import { useEffect, useState, type FormEvent } from 'react';
import { api, formatDate } from '../account';
import { t, tError } from '../i18n';
import { Link } from '../router';
import { ORG_APPS } from './OrgPage';

// Platform admin: churches and ministries that use CMGI Apps. Each gets its own page;
// while its plan runs, all of its members have Pro.

interface AdminOrg {
  id: string; slug: string; name: string; logo: string; color: string; welcome: string; apps: string[];
  plan: 'pro' | 'free'; pro_until: string | null; seats: number; price_note: string; disabled: boolean;
  created_at: string; members: number; pro_active: boolean;
}

const EMPTY = { name: '', slug: '', color: '#1764d8', apps: ['eventpass', 'sermon-ai', 'bodyofchrist'], plan: 'pro', pro_until: '', seats: 0, price_note: '', admin_email: '' };

function slugify(name: string) {
  return name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}

function AppChoice({ value, onChange }: { value: string[]; onChange: (apps: string[]) => void }) {
  return (
    <div className="chip-row">
      {Object.entries(ORG_APPS).map(([id, app]) => (
        <button type="button" key={id} className={`chip ${value.includes(id) ? 'active' : ''}`}
          onClick={() => onChange(value.includes(id) ? value.filter((a) => a !== id) : [...value, id])}>{app.name}</button>
      ))}
    </div>
  );
}

export function AdminOrgs() {
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [slugTouched, setSlugTouched] = useState(false);
  const [msg, setMsg] = useState<{ text: string; link?: string }>({ text: '' });
  const [open, setOpen] = useState<string | null>(null);

  async function load() { setOrgs(await api<AdminOrg[]>('/admin/orgs')); }
  useEffect(() => { load().catch((e) => setMsg({ text: tError(e.message) })); }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const body = { ...form, pro_until: form.pro_until ? new Date(`${form.pro_until}T23:59:00`).toISOString() : null };
      const org = await api<AdminOrg>('/admin/orgs', { method: 'POST', body });
      setForm(EMPTY); setSlugTouched(false);
      setMsg({ text: t('admin.created'), link: `/${org.slug}` });
      await load();
    } catch (err) { setMsg({ text: tError((err as Error).message) }); }
  }

  return (
    <>
      <p className="lead-small">{t('admin.orgsText')}</p>
      <div className="admin-layout">
        <div className="panel-card">
          <div className="table-wrap">
            <table className="admin-table">
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id} className={`${open === o.slug ? 'selected' : ''} ${o.disabled ? 'is-disabled' : ''}`} onClick={() => setOpen(o.slug)}>
                    <td><span className="org-dot" style={{ background: o.color }} /> <strong>{o.name}</strong><br /><small>/{o.slug}</small></td>
                    <td>{o.pro_active ? <span className="plan-badge pro">PRO</span> : <span className="plan-badge free">{t('admin.orgInactive')}</span>}
                      {o.disabled && <span className="tag warn">{t('admin.orgDisabled')}</span>}<br />
                      <small>{o.pro_until ? t('admin.histUntil', { date: formatDate(o.pro_until) }) : o.plan === 'pro' ? t('admin.histForever') : ''}</small></td>
                    <td><small>{t('admin.orgMembers', { n: o.members })}{o.seats ? ` / ${o.seats}` : ''}</small></td>
                  </tr>
                ))}
                {!orgs.length && <tr><td className="empty">{t('admin.orgNone')}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {open ? <OrgEditor key={open} org={orgs.find((o) => o.slug === open)!} onSaved={load} onClose={() => setOpen(null)} /> : (
          <form className="panel-card" onSubmit={create}>
            <h3>{t('admin.newOrg')}</h3>
            <label className="field">{t('admin.orgName')}<input required minLength={2} maxLength={120} value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value, slug: slugTouched ? form.slug : slugify(e.target.value) })} /></label>
            <label className="field">{t('admin.orgSlug')}
              <span className="slug-field"><span>{window.location.host}/</span>
                <input required pattern="[a-z0-9][a-z0-9-]{0,38}[a-z0-9]" maxLength={40} value={form.slug}
                  onChange={(e) => { setSlugTouched(true); setForm({ ...form, slug: e.target.value.toLowerCase() }); }} /></span></label>
            <span className="label-text">{t('admin.orgApps')}</span>
            <AppChoice value={form.apps} onChange={(apps) => setForm({ ...form, apps })} />
            <div className="two-col">
              <label className="field">{t('admin.orgPlan')}
                <select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}>
                  <option value="pro">{t('admin.planPro')}</option><option value="free">{t('admin.planFree')}</option>
                </select></label>
              <label className="field">{t('org.color')}<input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} /></label>
            </div>
            <div className="two-col">
              <label className="field">{t('admin.orgUntil')}<input type="date" value={form.pro_until} onChange={(e) => setForm({ ...form, pro_until: e.target.value })} /></label>
              <label className="field">{t('admin.orgSeats')}<input type="number" min={0} max={100000} value={form.seats} onChange={(e) => setForm({ ...form, seats: Number(e.target.value) })} /></label>
            </div>
            <label className="field">{t('admin.orgPrice')}<input maxLength={300} value={form.price_note} onChange={(e) => setForm({ ...form, price_note: e.target.value })} /></label>
            <label className="field">{t('admin.orgAdmin')}<input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} /></label>
            <button className="btn btn-primary btn-small">{t('admin.create')}</button>
            {msg.text && <p className="hint" role="status">{msg.text} {msg.link && <Link to={msg.link}>{window.location.host}{msg.link}</Link>}</p>}
          </form>
        )}
      </div>
    </>
  );
}

function OrgEditor({ org, onSaved, onClose }: { org: AdminOrg; onSaved: () => Promise<void>; onClose: () => void }) {
  const [form, setForm] = useState({
    name: org.name, apps: org.apps, plan: org.plan, pro_until: org.pro_until ? org.pro_until.slice(0, 10) : '',
    seats: org.seats, price_note: org.price_note,
  });
  const [adminEmail, setAdminEmail] = useState('');
  const [msg, setMsg] = useState('');

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      const body = { ...form, pro_until: form.pro_until ? new Date(`${form.pro_until}T23:59:00`).toISOString() : null, clear_pro_until: !form.pro_until };
      await api(`/admin/orgs/${org.slug}`, { method: 'PATCH', body }); await onSaved(); setMsg(t('org.saved'));
    } catch (err) { setMsg(tError((err as Error).message)); }
  }
  async function toggle() {
    try { await api(`/admin/orgs/${org.slug}`, { method: 'PATCH', body: { disabled: !org.disabled } }); await onSaved(); }
    catch (err) { setMsg(tError((err as Error).message)); }
  }
  async function inviteAdmin(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api<{ status: string; email: string }>(`/orgs/${org.slug}/invites`, { method: 'POST', body: { email: adminEmail, role: 'admin' } });
      setAdminEmail(''); setMsg(r.status === 'added' ? t('org.added', { email: r.email }) : t('org.invited', { email: r.email }));
    } catch (err) { setMsg(tError((err as Error).message)); }
  }

  return (
    <aside className="panel-card user-panel">
      <div className="auth-actions" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>{org.name}</h3>
        <Link to={`/${org.slug}`} className="btn btn-ghost btn-small">{t('admin.orgOpen')}</Link>
        <button className="btn btn-ghost btn-small" onClick={onClose}>×</button>
      </div>
      <p className="muted-line">/{org.slug} · {formatDate(org.created_at)} · {t('admin.orgMembers', { n: org.members })}</p>
      <form className="admin-block" onSubmit={save}>
        <label className="field">{t('admin.orgName')}<input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <span className="label-text">{t('admin.orgApps')}</span>
        <AppChoice value={form.apps} onChange={(apps) => setForm({ ...form, apps })} />
        <div className="two-col">
          <label className="field">{t('admin.orgPlan')}
            <select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value as 'pro' | 'free' })}>
              <option value="pro">{t('admin.planPro')}</option><option value="free">{t('admin.planFree')}</option>
            </select></label>
          <label className="field">{t('admin.orgUntil')}<input type="date" value={form.pro_until} onChange={(e) => setForm({ ...form, pro_until: e.target.value })} /></label>
        </div>
        <div className="two-col">
          <label className="field">{t('admin.orgSeats')}<input type="number" min={0} value={form.seats} onChange={(e) => setForm({ ...form, seats: Number(e.target.value) })} /></label>
          <label className="field">{t('admin.orgPrice')}<input maxLength={300} value={form.price_note} onChange={(e) => setForm({ ...form, price_note: e.target.value })} /></label>
        </div>
        <div className="auth-actions">
          <button className="btn btn-primary btn-small">{t('admin.orgSave')}</button>
          <button type="button" className="btn btn-ghost btn-small" onClick={toggle}>{org.disabled ? t('admin.orgEnable') : t('admin.orgDisable')}</button>
        </div>
      </form>
      <form className="admin-block" onSubmit={inviteAdmin}>
        <h4>{t('admin.orgInviteAdmin')}</h4>
        <label className="field">{t('auth.email')}<input required type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} /></label>
        <button className="btn btn-ghost btn-small">{t('org.inviteSend')}</button>
      </form>
      {msg && <p className="hint" role="status">{msg}</p>}
    </aside>
  );
}
