import { useState } from 'react';
import { APPS, STATUS_KEY, type AppStatus } from '../config/apps';
import { AppCard } from '../components/AppCard';
import { t } from '../i18n';
import { PageHead } from './PageHead';

const FILTERS: ('all' | AppStatus)[] = ['all', 'available', 'coming-soon', 'planned'];

export function Apps() {
  const [filter, setFilter] = useState<'all' | AppStatus>('all');
  const shown = APPS.filter((a) => filter === 'all' || a.status === filter);
  return (
    <>
      <PageHead eyebrow={t('apps.eyebrow')} title={t('apps.title')} text={t('apps.text')} />
      <section className="section section-tight">
        <div className="container">
          <div className="filter-bar" role="group" aria-label={t('apps.filter')}>
            {FILTERS.map((f) => (
              <button key={f} className={`chip ${filter === f ? 'active' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === 'all' ? t('apps.all') : t(STATUS_KEY[f])}
                <span>{f === 'all' ? APPS.length : APPS.filter((a) => a.status === f).length}</span>
              </button>
            ))}
          </div>
          <div className="app-grid" key={filter}>
            {shown.map((app) => <AppCard key={app.id} app={app} />)}
          </div>
        </div>
      </section>
    </>
  );
}
