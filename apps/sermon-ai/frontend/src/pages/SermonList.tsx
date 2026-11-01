import { useEffect, useState } from 'react';
import { formatDate, formatDuration, LANGS, request, type Lang, type SermonSummary } from '../api';
import { Link, navigate } from '../router';
import { StatusPill } from './StatusPill';

export function SermonList() {
  const [sermons, setSermons] = useState<SermonSummary[] | null>(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ title: '', preacher: '', sermon_date: new Date().toLocaleDateString('en-CA'), language: 'auto' });

  useEffect(() => { request<SermonSummary[]>('/sermons').then(setSermons).catch((e) => setError(e.message)); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const { id } = await request<{ id: string }>('/sermons', { method: 'POST', body: form });
      navigate(`/sermons/${id}/record`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main className="container">
      <div className="page-title">
        <h1>Sermons</h1>
        <p className="muted">Record a sermon in the browser, then turn it into a transcript, a structured report and translations.</p>
      </div>
      {error && <p className="alert error">{error}</p>}
      <div className="layout-2">
        <section className="card">
          <h2>New recording</h2>
          <form onSubmit={create}>
            <label>Title<input required minLength={2} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Sunday service – Faith that moves" /></label>
            <label>Preacher<input value={form.preacher} onChange={(e) => setForm({ ...form, preacher: e.target.value })} placeholder="Optional" /></label>
            <div className="row-2">
              <label>Date<input type="date" required value={form.sermon_date} onChange={(e) => setForm({ ...form, sermon_date: e.target.value })} /></label>
              <label>Spoken language
                <select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                  <option value="auto">Detect automatically</option>
                  {(Object.keys(LANGS) as Lang[]).map((l) => <option key={l} value={l}>{LANGS[l]}</option>)}
                </select>
              </label>
            </div>
            <button className="btn btn-primary btn-block">● Continue to recording</button>
          </form>
        </section>
        <section>
          {sermons === null && !error && <p className="muted">Loading…</p>}
          {sermons?.length === 0 && <div className="card empty"><p>No sermons yet. Your first recording will appear here.</p></div>}
          <div className="list">
            {sermons?.map((s) => (
              <Link key={s.id} to={`/sermons/${s.id}`} className="list-item">
                <div>
                  <strong>{s.title}</strong>
                  <span className="muted small">
                    {formatDate(s.sermon_date)}{s.preacher && ` · ${s.preacher}`}{s.duration_s > 0 && ` · ${formatDuration(s.duration_s)}`}
                    {s.report_languages && ` · Reports: ${s.report_languages.split(',').map((l) => l.toUpperCase()).join(', ')}`}
                  </span>
                  {s.error && <span className="small text-error">{s.error}</span>}
                </div>
                <StatusPill status={s.status} />
              </Link>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
