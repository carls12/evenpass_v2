import { Icon } from '../components/Icon';
import { t } from '../i18n';
import { Link } from '../router';
import { PageHead } from './PageHead';

export function About() {
  return (
    <>
      <PageHead eyebrow={t('about.eyebrow')} title={t('about.title')} text={t('about.text')} />
      <section className="section section-tight">
        <div className="container prose-grid">
          <div className="prose reveal">
            <h2>{t('about.whyTitle')}</h2>
            <p>{t('about.whyText')}</p>
            <h2>{t('about.howTitle')}</h2>
            <p>{t('about.howText')}</p>
            <h2>{t('about.whereTitle')}</h2>
            <p>{t('about.whereText')}</p>
            <Link to="/apps" className="btn btn-primary">{t('about.seeAll')} <Icon name="arrow" size={18} /></Link>
          </div>
          <aside className="fact-card reveal">
            <h3>{t('about.glance')}</h3>
            <ul>
              <li><Icon name="grid" size={18} /> {t('about.f1')}</li>
              <li><Icon name="server" size={18} /> {t('about.f2')}</li>
              <li><Icon name="lock" size={18} /> {t('about.f3')}</li>
              <li><Icon name="scan" size={18} /> {t('about.f4')}</li>
            </ul>
          </aside>
        </div>
      </section>
    </>
  );
}
