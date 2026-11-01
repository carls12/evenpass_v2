import { APPS } from '../config/apps';
import { AppCard } from '../components/AppCard';
import { Icon, type IconName } from '../components/Icon';
import { Link } from '../router';

const PILLARS: { icon: IconName; title: string; text: string }[] = [
  { icon: 'heart', title: 'Built for ministry', text: 'Tools shaped around conferences, services and community life — not generic business software.' },
  { icon: 'shield', title: 'Your data, your server', text: 'Self-hosted on infrastructure we control. Participant data is not shared with third-party platforms.' },
  { icon: 'grid', title: 'One home for every app', text: 'Each application stays independent, yet all of them live under one address and one design.' },
];

export function Home() {
  const live = APPS.find((a) => a.status === 'available' && a.href);
  return (
    <>
      <section className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="container hero-inner">
          <div className="hero-copy">
            <span className="eyebrow">Digital tools for church &amp; community</span>
            <h1>
              CMGI Apps
              <span className="hero-sub">Digital Solutions for Ministry and Community</span>
            </h1>
            <p className="lead">One platform. Multiple applications. One mission.</p>
            <div className="hero-actions">
              <Link to="/apps" className="btn btn-primary">Explore applications <Icon name="arrow" size={18} /></Link>
              {live && <a href={live.href} className="btn btn-ghost">Open {live.name}</a>}
            </div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            {APPS.map((app, i) => (
              <div key={app.id} className={`hero-tile tile-${i}`}>
                <span className="app-icon"><Icon name={app.icon} size={24} /></span>
                <div>
                  <strong>{app.name}</strong>
                  <small>{app.status === 'available' ? 'Live now' : app.status === 'coming-soon' ? 'In development' : 'On the roadmap'}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head reveal">
            <span className="eyebrow">Applications</span>
            <h2>Everything in one place</h2>
            <p>Start with what is available today — more applications are on the way.</p>
          </div>
          <div className="app-grid">
            {APPS.map((app) => <AppCard key={app.id} app={app} />)}
          </div>
        </div>
      </section>

      <section className="section section-tint">
        <div className="container">
          <div className="section-head reveal">
            <span className="eyebrow">Why CMGI Apps</span>
            <h2>Made for the way we serve</h2>
          </div>
          <div className="pillar-grid">
            {PILLARS.map((p) => (
              <div className="pillar reveal" key={p.title}>
                <span className="pillar-icon"><Icon name={p.icon} /></span>
                <h3>{p.title}</h3>
                <p>{p.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {live && (
        <section className="section">
          <div className="container">
            <div className="cta-band reveal">
              <div>
                <h2>Planning an event?</h2>
                <p>Create the event, share the registration link and check guests in with a phone camera.</p>
              </div>
              <a href={live.href} className="btn btn-light">Open {live.name} <Icon name="arrow" size={18} /></a>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
