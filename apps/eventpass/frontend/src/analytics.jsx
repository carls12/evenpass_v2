import { useEffect, useState } from 'react';

// Analysis of one event: key numbers, attendance per day, by category; Excel and PDF downloads.
const show = (day) => (day ? day.split('-').reverse().join('.') : '');

function Bars({ items, label, value, max, suffix }) {
  return (
    <div className="bars">
      {items.map((item) => (
        <div className="bar-row" key={label(item)}>
          <span className="bar-label" title={label(item)}>{label(item)}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${max ? Math.max(2, (100 * value(item)) / max) : 0}%` }} /></span>
          <span className="bar-value">{value(item)}{suffix ? suffix(item) : ''}</span>
        </div>
      ))}
    </div>
  );
}

export function EventAnalysis({ api, eventId, title, token, refreshKey, saveBlob }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const headers = token ? { Authorization: 'Bearer ' + token } : {};

  useEffect(() => {
    let active = true;
    fetch(`${api}/events/${eventId}/analysis`, { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('Auswertung konnte nicht geladen werden'))))
      .then((d) => { if (active) { setData(d); setError(''); } }, (e) => active && setError(e.message));
    return () => { active = false; };
  }, [eventId, refreshKey]);

  async function download(kind) {
    setBusy(kind); setError('');
    try {
      const r = await fetch(`${api}/events/${eventId}/report.${kind}`, { headers });
      if (!r.ok) throw new Error('Download fehlgeschlagen');
      const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'event';
      saveBlob(await r.blob(), `auswertung-${slug}.${kind}`);
    } catch (e) { setError(e.message); } finally { setBusy(''); }
  }

  return (
    <section className="analysis panel">
      <div className="top">
        <h3>📈 Auswertung</h3>
        <div className="actions">
          <button type="button" disabled={!!busy} onClick={() => download('xlsx')}>{busy === 'xlsx' ? 'Wird erstellt …' : '⬇ Excel (Liste & Auswertung)'}</button>
          <button type="button" className="secondary" disabled={!!busy} onClick={() => download('pdf')}>{busy === 'pdf' ? 'Wird erstellt …' : '⬇ PDF-Bericht'}</button>
        </div>
      </div>
      <p className="hint">Die Excel-Datei enthält drei Blätter: Übersicht, alle Teilnehmer mit ihren Antworten und einer Spalte pro Event-Tag (✓ / –) sowie alle Check-ins mit Uhrzeit.</p>
      {error && <p className="err">{error}</p>}
      {data && <>
        <div className="metrics">
          <div><strong>{data.registered}</strong><span>Angemeldet</span></div>
          <div><strong>{data.checked_in}</strong><span>Eingecheckt (mind. 1 Tag)</span></div>
          <div><strong>{data.not_checked_in}</strong><span>Nicht erschienen</span></div>
          <div><strong>{data.rate} %</strong><span>Teilnahmequote</span></div>
        </div>
        <div className="analysis-grid">
          <div>
            <h4>Anwesenheit pro Tag</h4>
            <Bars items={data.per_day} label={(d) => show(d.day)} value={(d) => d.count} max={data.registered} suffix={(d) => ` (${d.rate} %)`} />
          </div>
          <div>
            <h4>Nach Kategorie / Rolle</h4>
            <Bars items={data.by_category} label={(g) => g.name} value={(g) => g.checked_in}
              max={Math.max(1, ...data.by_category.map((g) => g.registered))} suffix={(g) => ` / ${g.registered}`} />
          </div>
          {data.signups_by_date.length > 0 && <div>
            <h4>Anmeldungen pro Tag</h4>
            <Bars items={data.signups_by_date.slice(-10)} label={(s) => show(s.date)} value={(s) => s.count}
              max={Math.max(...data.signups_by_date.map((s) => s.count))} />
          </div>}
        </div>
      </>}
    </section>
  );
}
