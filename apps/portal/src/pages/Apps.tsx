import { useState } from 'react';
import { APPS, STATUS_LABEL, type AppStatus } from '../config/apps';
import { AppCard } from '../components/AppCard';
import { PageHead } from './PageHead';

const FILTERS: ('all' | AppStatus)[] = ['all', 'available', 'coming-soon', 'planned'];

export function Apps() {
  const [filter, setFilter] = useState<'all' | AppStatus>('all');
  const shown = APPS.filter((a) => filter === 'all' || a.status === filter);
  return (
    <>
      <PageHead eyebrow="Applications" title="All applications" text="Every CMGI application in one overview. Only apps marked Available can be opened today." />
      <section className="section section-tight">
        <div className="container">
          <div className="filter-bar" role="group" aria-label="Filter by status">
            {FILTERS.map((f) => (
              <button key={f} className={`chip ${filter === f ? 'active' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === 'all' ? 'All' : STATUS_LABEL[f]}
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
