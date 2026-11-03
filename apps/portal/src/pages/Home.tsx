import { APPS } from '../config/apps';
import { AppCard } from '../components/AppCard';
import { Icon, type IconName } from '../components/Icon';
import { t } from '../i18n';
import type { Key } from '../i18n/en';
import { Link } from '../router';

const PILLARS: { icon: IconName; title: Key; text: Key }[] = [
  { icon: 'heart', title: 'home.p1.title', text: 'home.p1.text' },
  { icon: 'shield', title: 'home.p2.title', text: 'home.p2.text' },
  { icon: 'grid', title: 'home.p3.title', text: 'home.p3.text' },
];

export function Home() {
  const live = APPS.find((a) => a.status === 'available' && a.href);
  return (
    <>
      <section className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="container hero-inner">
          <div className="hero-copy">
            <span className="eyebrow">{t('home.eyebrow')}</span>
            <h1>
              CMGI Apps
              <span className="hero-sub">{t('site.subtitle')}</span>
            </h1>
            <p className="lead">{t('site.tagline')}</p>
            <div className="hero-actions">
              <Link to="/apps" className="btn btn-primary">{t('home.explore')} <Icon name="arrow" size={18} /></Link>
              {live && <a href={live.href} className="btn btn-ghost">{t('card.open', { name: live.name })}</a>}
            </div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            {APPS.map((app, i) => (
              <div key={app.id} className={`hero-tile tile-${i}`}>
                <span className="app-icon"><Icon name={app.icon} size={24} /></span>
                <div>
                  <strong>{app.name}</strong>
                  <small>{t(app.status === 'available' ? 'home.liveNow' : app.status === 'coming-soon' ? 'home.inDevelopment' : 'home.roadmap')}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head reveal">
            <span className="eyebrow">{t('home.appsEyebrow')}</span>
            <h2>{t('home.appsTitle')}</h2>
            <p>{t('home.appsText')}</p>
          </div>
          <div className="app-grid">
            {APPS.map((app) => <AppCard key={app.id} app={app} />)}
          </div>
        </div>
      </section>

      <section className="section section-tint">
        <div className="container">
          <div className="section-head reveal">
            <span className="eyebrow">{t('home.whyEyebrow')}</span>
            <h2>{t('home.whyTitle')}</h2>
          </div>
          <div className="pillar-grid">
            {PILLARS.map((p) => (
              <div className="pillar reveal" key={p.title}>
                <span className="pillar-icon"><Icon name={p.icon} /></span>
                <h3>{t(p.title)}</h3>
                <p>{t(p.text)}</p>
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
                <h2>{t('home.ctaTitle')}</h2>
                <p>{t('home.ctaText')}</p>
              </div>
              <a href={live.href} className="btn btn-light">{t('card.open', { name: live.name })} <Icon name="arrow" size={18} /></a>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
