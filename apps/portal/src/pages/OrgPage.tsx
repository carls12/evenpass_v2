import { useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { api, formatDate, refreshAccount, useAccount } from '../account';
import { Icon, type IconName } from '../components/Icon';
import { t, tError } from '../i18n';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

// The page of a church or ministry that uses CMGI Apps: cmgi-apps.de/<slug>.
// Everyone sees its name and logo; members open its apps; its admins manage people and the page.

interface PublicOrg { slug: string; name: string; logo: string; color: string; welcome: string; apps: string[]; active: boolean }
interface Member { id: string; name: string; email: string; role: 'admin' | 'member'; joined: string }
interface OrgDetail extends PublicOrg {
  role: 'admin' | 'member' | null; pro_active: boolean; can_manage: boolean;
  members?: Member[]; invites?: { email: string; role: string; created_at: string }[]; join_code?: string; seats?: number; pro_until?: string | null;
}

export const ORG_APPS: Record<string, { name: string; href?: string; icon: IconName }> = {
  eventpass: { name: 'EventPass Studio', href: '/eventpass/', icon: 'ticket' },
  'sermon-ai': { name: 'Sermon Intelligence', href: '/sermon-ai/', icon: 'waveform' },
  bodyofchrist: { name: 'Body of Christ', href: '/bodyofchrist/', icon: 'heart' },
  projection: { name: 'ChurchProjection Studio', icon: 'screen' },
};

export function OrgPage({ slug }: { slug: string }) {
  const { account, loading } = useAccount();
  const [org, setOrg] = useState<PublicOrg | null | undefined>(undefined);
  const [detail, setDetail] = useState<OrgDetail | null>(null);
  const [msg, setMsg] = useState('');
  const join = new URLSearchParams(window.location.search).get('join') || '';

  useEffect(() => { api<PublicOrg>(`/orgs/${slug}/public`).then(setOrg, () => setOrg(null)); }, [slug]);
  async function loadDetail() { setDetail(await api<OrgDetail>(`/orgs/${slug}`)); }
  useEffect(() => { if (account && org) loadDetail().catch(() => setDetail(null)); }, [account?.id, org?.slug]);
  useEffect(() => { if (org) document.title = `${org.name} · CMGI Apps`; }, [org]);

  if (org === undefined || loading) return <PageHead eyebrow="CMGI Apps" title={t('account.loading')} />;
  if (org === null) {
    return <>
      <PageHead eyebrow="404" title={t('notFound.title')} text={t('org.notFound')} />
      <section className="section section-tight"><div className="container"><Link to="/" className="btn btn-primary">{t('notFound.back')}</Link></div></section>
    </>;
  }

  async function joinNow() {
    try {
      await api(`/orgs/${slug}/join`, { method: 'POST', body: { code: join } });
      await Promise.all([loadDetail(), refreshAccount()]);
      setMsg(t('org.joined', { name: org!.name }));
      window.history.replaceState({}, '', `/${slug}`);
    } catch (err) { setMsg(tError((err as Error).message)); }
  }

  const member = !!detail?.role;
  const here = `/${slug}${join ? `?join=${encodeURIComponent(join)}` : ''}`;
  return (
    <>
      <section className="org-hero" style={{ '--org': org.color } as CSSProperties}>
        <div className="container org-hero-inner">
          {org.logo ? <img className="org-logo" src={org.logo} alt="" /> : <span className="org-logo org-initial">{org.name.charAt(0)}</span>}
          <div>
            <span className="eyebrow">CMGI Apps</span>
            <h1>{org.name}</h1>
            {org.welcome && <p className="lead org-welcome">{org.welcome}</p>}
          </div>
        </div>
      </section>

      <section className="section section-tight">
        <div className="container org-layout">
          {msg && <p className="banner banner-ok">{msg}</p>}
          {!account ? (
            <div className="panel-card org-cta">
              <p>{t('org.signInToJoin', { name: org.name })}</p>
              <div className="auth-actions">
                <Link to={`/login?next=${encodeURIComponent(here)}`} className="btn btn-primary">{t('nav.signIn')}</Link>
                <Link to={`/register?next=${encodeURIComponent(here)}`} className="btn btn-ghost">{t('auth.tabRegister')}</Link>
              </div>
            </div>
          ) : member ? (
            <p className="banner banner-ok">{t('org.member', { name: org.name })} {detail?.pro_active && t('org.proActive')}</p>
          ) : join ? (
            <div className="panel-card org-cta"><button className="btn btn-primary" onClick={joinNow}>{t('org.join', { name: org.name })}</button></div>
          ) : detail && !detail.can_manage ? (
            <p className="banner banner-warn">{t('org.notMember', { name: org.name })}</p>
          ) : null}

          <h2 className="org-section-title">{t('org.yourApps')}</h2>
          <div className="org-apps">
            {org.apps.map((id) => {
              const app = ORG_APPS[id];
              if (!app) return null;
              const open = app.href && (member || detail?.can_manage);
              return (
                <div key={id} className="org-app">
                  <span className="app-icon"><Icon name={app.icon} size={24} /></span>
                  <strong>{app.name}</strong>
                  {open ? <a className="btn btn-primary btn-small" href={app.href}>{t('card.open', { name: app.name })} <Icon name="arrow" size={16} /></a>
                    : !app.href ? <span className="status-pill status-coming-soon">{t('org.soon')}</span> : null}
                </div>
              );
            })}
          </div>

          {detail?.can_manage && <ManagePanel detail={detail} reload={loadDetail} />}
          {member && !detail?.can_manage && account && (
            <button className="btn btn-ghost btn-small" onClick={async () => {
              if (!confirm(t('org.confirmLeave', { name: org.name }))) return;
              try { await api(`/orgs/${slug}/members/${account.id}`, { method: 'DELETE' }); await refreshAccount(); navigate('/account'); }
              catch (err) { setMsg(tError((err as Error).message)); }
            }}>{t('org.leave')}</button>
          )}
        </div>
      </section>
    </>
  );
}

function ManagePanel({ detail, reload }: { detail: OrgDetail; reload: () => Promise<void> }) {
  const { account } = useAccount();
  const [invite, setInvite] = useState({ email: '', role: 'member' });
  const [msg, setMsg] = useState('');
  const [copied, setCopied] = useState(false);
  const [brand, setBrand] = useState({ logo: detail.logo, color: detail.color, welcome: detail.welcome });
  const members = detail.members ?? [];
  const joinLink = `${window.location.origin}/${detail.slug}?join=${detail.join_code}`;

  async function act(fn: () => Promise<unknown>, ok = '') {
    try { await fn(); await reload(); setMsg(ok); } catch (err) { setMsg(tError((err as Error).message)); }
  }
  async function sendInvite(e: FormEvent) {
    e.preventDefault();
    await act(async () => {
      const r = await api<{ status: string; email: string }>(`/orgs/${detail.slug}/invites`, { method: 'POST', body: invite });
      setInvite({ email: '', role: 'member' });
      setMsg(r.status === 'added' ? t('org.added', { email: r.email }) : t('org.invited', { email: r.email }));
    });
  }
  function upload(file: File | undefined) {
    if (!file) return;
    if (file.size > 300_000) { setMsg(t('org.tooBig')); return; }
    const reader = new FileReader();
    reader.onload = () => setBrand((b) => ({ ...b, logo: String(reader.result) }));
    reader.readAsDataURL(file);
  }

  return (
    <div className="org-manage">
      <h2 className="org-section-title">{t('org.manage', { name: detail.name })}</h2>
      {msg && <p className="hint" role="status">{msg}</p>}
      <div className="org-manage-grid">
        <article className="panel-card wide">
          <h3>{t('org.members', { n: members.length })}</h3>
          {!!detail.seats && <p className="hint">{t('org.seats', { n: members.length, max: detail.seats })}</p>}
          <div className="table-wrap">
            <table className="admin-table">
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td><strong>{m.name}</strong><br /><small>{m.email}</small></td>
                    <td><span className={`tag ${m.role === 'admin' ? '' : 'muted'}`}>{m.role === 'admin' ? t('org.roleAdmin') : t('org.roleMember')}</span></td>
                    <td><small>{formatDate(m.joined)}</small></td>
                    <td className="row-actions">
                      <button className="btn btn-ghost btn-small" onClick={() => act(() => api(`/orgs/${detail.slug}/members/${m.id}`, { method: 'PATCH', body: { role: m.role === 'admin' ? 'member' : 'admin' } }))}>
                        {m.role === 'admin' ? t('org.makeMember') : t('org.makeAdmin')}
                      </button>
                      {m.id !== account?.id && (
                        <button className="btn btn-ghost btn-small" onClick={() => { if (confirm(t('org.confirmRemove', { name: m.name }))) act(() => api(`/orgs/${detail.slug}/members/${m.id}`, { method: 'DELETE' })); }}>{t('org.remove')}</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <form className="panel-card" onSubmit={sendInvite}>
          <h3>{t('org.invite')}</h3>
          <label className="field">{t('auth.email')}<input required type="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></label>
          <div className="chip-row">
            {(['member', 'admin'] as const).map((r) => (
              <button type="button" key={r} className={`chip ${invite.role === r ? 'active' : ''}`} onClick={() => setInvite({ ...invite, role: r })}>{r === 'admin' ? t('org.roleAdmin') : t('org.roleMember')}</button>
            ))}
          </div>
          <button className="btn btn-primary btn-small">{t('org.inviteSend')}</button>
          {!!detail.invites?.length && <>
            <h4>{t('org.pending')}</h4>
            <ul className="history">
              {detail.invites.map((i) => (
                <li key={i.email}>{i.email} · {i.role === 'admin' ? t('org.roleAdmin') : t('org.roleMember')}{' '}
                  <button type="button" className="link-button" onClick={() => act(() => api(`/orgs/${detail.slug}/invites?email=${encodeURIComponent(i.email)}`, { method: 'DELETE' }))}>{t('org.cancel')}</button>
                </li>
              ))}
            </ul>
          </>}
        </form>

        <article className="panel-card">
          <h3>{t('org.joinLink')}</h3>
          <p className="hint">{t('org.joinLinkHint')}</p>
          <textarea className="copy-box" readOnly rows={2} value={joinLink} onFocus={(e) => e.target.select()} />
          <div className="auth-actions">
            <button className="btn btn-primary btn-small" onClick={() => navigator.clipboard?.writeText(joinLink).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })}>{copied ? t('org.copied') : t('org.copy')}</button>
            <button className="btn btn-ghost btn-small" onClick={() => { if (confirm(t('org.newLinkConfirm'))) act(() => api(`/orgs/${detail.slug}/join-code`, { method: 'POST' })); }}>{t('org.newLink')}</button>
          </div>
        </article>

        <form className="panel-card" onSubmit={(e) => { e.preventDefault(); act(() => api(`/orgs/${detail.slug}`, { method: 'PATCH', body: brand }), t('org.saved')); }}>
          <h3>{t('org.page')}</h3>
          <label className="field">{t('org.logo')}<input value={brand.logo.startsWith('data:') ? '' : brand.logo} placeholder="https://…" onChange={(e) => setBrand({ ...brand, logo: e.target.value })} />
            <small>{t('org.logoHint')}</small></label>
          <div className="auth-actions">
            {brand.logo && <img className="org-logo small" src={brand.logo} alt="" />}
            <label className="btn btn-ghost btn-small">{t('org.upload')}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => upload(e.target.files?.[0])} /></label>
          </div>
          <label className="field">{t('org.color')}<input type="color" value={brand.color} onChange={(e) => setBrand({ ...brand, color: e.target.value })} /></label>
          <label className="field">{t('org.welcome')}<textarea rows={3} maxLength={2000} value={brand.welcome} onChange={(e) => setBrand({ ...brand, welcome: e.target.value })} /></label>
          <button className="btn btn-primary btn-small">{t('org.saveBrand')}</button>
        </form>
      </div>
    </div>
  );
}
