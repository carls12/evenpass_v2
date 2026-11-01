import { STATUS_LABEL, type PlatformApp } from '../config/apps';
import { Icon } from './Icon';

export function AppCard({ app }: { app: PlatformApp }) {
  const live = app.status === 'available' && app.href;
  return (
    <article className={`app-card reveal ${live ? 'is-live' : 'is-upcoming'}`}>
      <div className="app-card-top">
        <span className="app-icon"><Icon name={app.icon} size={26} /></span>
        <span className={`status-pill status-${app.status}`}>{STATUS_LABEL[app.status]}</span>
      </div>
      <h3>{app.name}</h3>
      <p>{app.description}</p>
      {!live && <p className="scope-label">Planned scope</p>}
      <ul className="app-highlights">
        {app.highlights.map((h) => <li key={h}>{h}</li>)}
      </ul>
      {live ? (
        <a className="btn btn-primary app-cta" href={app.href}>
          Open {app.name} <Icon name="arrow" size={18} />
        </a>
      ) : (
        <span className="btn btn-disabled app-cta" aria-disabled="true">Not yet available</span>
      )}
    </article>
  );
}
