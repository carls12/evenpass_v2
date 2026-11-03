import { useEffect, useState } from 'react';
import { STATUS_KEY, type PlatformApp } from '../config/apps';
import { t } from '../i18n';
import { Icon } from './Icon';

// One check per page load and app, shared by all cards.
const probes = new Map<string, Promise<boolean>>();
function isRunning(url: string) {
  if (!probes.has(url)) probes.set(url, fetch(url, { cache: 'no-store' }).then((r) => r.ok, () => false));
  return probes.get(url)!;
}

export function AppCard({ app: configured }: { app: PlatformApp }) {
  const [app, setApp] = useState(configured);
  useEffect(() => {
    const probe = configured.probe;
    if (!probe) return;
    let active = true;
    isRunning(probe.url).then((ok) => { if (ok && active) setApp({ ...configured, status: 'available', href: probe.href }); });
    return () => { active = false; };
  }, [configured]);
  const live = app.status === 'available' && app.href;
  return (
    <article className={`app-card reveal ${live ? 'is-live' : 'is-upcoming'}`}>
      <div className="app-card-top">
        <span className="app-icon"><Icon name={app.icon} size={26} /></span>
        <span className={`status-pill status-${app.status}`}>{t(STATUS_KEY[app.status])}</span>
      </div>
      <h3>{app.name}</h3>
      <p>{t(app.description)}</p>
      {!live && <p className="scope-label">{t('card.plannedScope')}</p>}
      <ul className="app-highlights">
        {app.highlights.map((h) => <li key={h}>{t(h)}</li>)}
      </ul>
      {live ? (
        <a className="btn btn-primary app-cta" href={app.href}>
          {t('card.open', { name: app.name })} <Icon name="arrow" size={18} />
        </a>
      ) : (
        <span className="btn btn-disabled app-cta" aria-disabled="true">{t('card.notYet')}</span>
      )}
    </article>
  );
}
