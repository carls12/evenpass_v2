import { useCallback, useEffect, useState } from 'react';
import { fetchBlob, formatDate, formatDuration, LANGS, request, saveBlob, type Lang, type Output, type Report, type Sermon, type ServiceStatus } from '../api';
import { Link, navigate } from '../router';
import { useQueue } from '../useQueue';
import { StatusPill } from './StatusPill';

const ALL_LANGS = Object.keys(LANGS) as Lang[];

/** Rough cost hints so nobody is surprised by the bill (USD, list prices at time of writing). */
function costHint(minutes: number, languages: number, translate: boolean) {
  const scale = Math.max(minutes, 10) / 60;
  return (languages * 0.3 * scale + (translate ? languages * 0.3 * scale : 0)).toFixed(2);
}

export function SermonPage({ id }: { id: string }) {
  const [sermon, setSermon] = useState<Sermon | null>(null);
  const [service, setService] = useState<ServiceStatus | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const queue = useQueue();
  const pending = queue?.pendingBySermon[id] ?? 0;

  const load = useCallback(() => request<Sermon>(`/sermons/${id}`).then(setSermon).catch((e) => setError(e.message)), [id]);
  useEffect(() => { void load(); request<ServiceStatus>('/status').then(setService).catch(() => {}); }, [load]);

  const busy = sermon?.status === 'transcribing' || sermon?.status === 'analyzing';
  useEffect(() => {
    if (!busy && !(sermon?.status === 'recording' && pending > 0)) return;
    const t = window.setInterval(() => void load(), 3000);
    return () => clearInterval(t);
  }, [busy, sermon?.status, pending, load]);
  // When the last queued upload (the "finish" marker) arrives, refresh once.
  useEffect(() => { if (pending === 0) void load(); }, [pending, load]);

  async function action(path: string, body?: unknown, method = 'POST') {
    setError(''); setNotice('');
    try {
      await request(path, { method, body });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!sermon) return <main className="container">{error ? <p className="alert error">{error}</p> : <p className="muted">Loading…</p>}</main>;

  const minutes = sermon.duration_s / 60;
  const hasAudio = sermon.segments.some((s) => s.bytes > 0);
  const canTranscribe = ['recorded', 'transcribed', 'done'].includes(sermon.status) && hasAudio && pending === 0;
  const hasTranscript = ['transcribed', 'done', 'analyzing'].includes(sermon.status);

  return (
    <main className="container">
      <Link to="/" className="back">← All sermons</Link>
      <div className="page-title split">
        <div>
          <h1>{sermon.title}</h1>
          <p className="muted">
            {formatDate(sermon.sermon_date)}{sermon.preacher && ` · ${sermon.preacher}`}
            {sermon.duration_s > 0 && ` · ${formatDuration(sermon.duration_s)}`}
            {` · ${sermon.language === 'auto' ? 'Language detected automatically' : LANGS[sermon.language]}`}
          </p>
        </div>
        <StatusPill status={sermon.status} />
      </div>

      {error && <p className="alert error">{error}</p>}
      {notice && <p className="alert ok">{notice}</p>}
      {sermon.error && !busy && <p className="alert error">{sermon.error}</p>}
      {busy && <p className="alert busy"><span className="spinner" /> {sermon.progress || 'Working…'} — you can leave this page; it continues on the server.</p>}
      {service && !service.transcription_configured && <p className="alert warn">Transcription is not set up on the server yet (OPENAI_API_KEY missing).</p>}
      {service && !service.analysis_configured && <p className="alert warn">Reports and translations are not set up on the server yet (ANTHROPIC_API_KEY missing).</p>}

      {/* ---------- Step 1: recording */}
      <section className="card step">
        <h2><span className="step-no">1</span> Recording</h2>
        {pending > 0 && <p className="alert busy"><span className="spinner" /> {pending} recorded part(s) are still uploading from this device. Keep this page open.</p>}
        {sermon.status === 'recording' && !hasAudio && pending === 0 && <p className="muted">Nothing recorded yet.</p>}
        <AudioParts sermon={sermon} />
        <div className="actions">
          {(sermon.status === 'recording' || sermon.status === 'recorded') && (
            <Link to={`/sermons/${id}/record`} className="btn btn-ghost">● {hasAudio ? 'Record more' : 'Start recording'}</Link>
          )}
          {sermon.status === 'recording' && hasAudio && pending === 0 && (
            <button className="btn btn-ghost" onClick={() => action(`/sermons/${id}/finish`, { duration_s: sermon.duration_s })}>Mark recording as finished</button>
          )}
        </div>
      </section>

      {/* ---------- Step 2: transcript */}
      <section className="card step">
        <h2><span className="step-no">2</span> Transcript</h2>
        {!hasTranscript && sermon.status !== 'transcribing' && (
          <>
            <p className="muted">Turns the recording into text with OpenAI ({service?.transcribe_model ?? 'whisper-1'}). About ${(Math.max(minutes, 1) * 0.006).toFixed(2)} for this recording.</p>
            <button className="btn btn-primary" disabled={!canTranscribe} onClick={() => action(`/sermons/${id}/transcribe`)}>Transcribe recording</button>
            {sermon.status === 'recording' && hasAudio && <p className="muted small">Finish the recording first.</p>}
          </>
        )}
        {hasTranscript && <TranscriptEditor sermon={sermon} onSaved={() => { setNotice('Transcript saved.'); void load(); }} onError={setError}
          onRetranscribe={() => { if (confirm('Transcribe again? This replaces the current transcript, including your corrections.')) void action(`/sermons/${id}/transcribe`); }}
          canRetranscribe={canTranscribe} />}
      </section>

      {/* ---------- Step 3: reports */}
      <section className="card step">
        <h2><span className="step-no">3</span> Reports &amp; translations</h2>
        {!hasTranscript ? <p className="muted">Available once the transcript is ready.</p> : (
          <AnalyzeForm sermon={sermon} minutes={minutes} model={service?.claude_model} disabled={busy}
            onStart={(languages, translate) => action(`/sermons/${id}/analyze`, { languages, translate })} />
        )}
        {sermon.outputs.length > 0 && <Outputs sermon={sermon} onError={setError} />}
      </section>

      <div className="danger-zone">
        <button className="link-danger" disabled={busy} onClick={async () => {
          if (!confirm(`Delete "${sermon.title}" including the audio, transcript and reports? This cannot be undone.`)) return;
          try { await request(`/sermons/${id}`, { method: 'DELETE' }); navigate('/'); } catch (e) { setError((e as Error).message); }
        }}>Delete this sermon</button>
      </div>
    </main>
  );
}

function AudioParts({ sermon }: { sermon: Sermon }) {
  const [urls, setUrls] = useState<Record<number, string>>({});
  const parts = sermon.segments.filter((s) => s.bytes > 0);
  useEffect(() => () => Object.values(urls).forEach(URL.revokeObjectURL), [urls]);
  if (!parts.length) return null;
  return (
    <div className="parts">
      {parts.map((s, i) => (
        <div className="part" key={s.idx}>
          <span>Part {i + 1} · {s.bytes >= 1_000_000 ? `${(s.bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(s.bytes / 1000))} KB`}</span>
          {urls[s.idx]
            ? <audio controls src={urls[s.idx]} preload="metadata" />
            : <button className="btn btn-small btn-ghost" onClick={async () => {
                const blob = await fetchBlob(`/sermons/${sermon.id}/segments/${s.idx}/audio`);
                setUrls((u) => ({ ...u, [s.idx]: URL.createObjectURL(blob) }));
              }}>▶ Listen</button>}
        </div>
      ))}
    </div>
  );
}

function TranscriptEditor({ sermon, onSaved, onError, onRetranscribe, canRetranscribe }: {
  sermon: Sermon; onSaved: () => void; onError: (m: string) => void; onRetranscribe: () => void; canRetranscribe: boolean;
}) {
  const [text, setText] = useState(sermon.transcript);
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setText(sermon.transcript); }, [sermon.transcript, editing]);
  const words = sermon.transcript.split(/\s+/).filter(Boolean).length;
  return (
    <>
      <p className="muted small">{words.toLocaleString()} words. Correct names and Bible references here before writing reports.</p>
      {editing ? (
        <>
          <textarea className="transcript" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="actions">
            <button className="btn btn-primary" onClick={async () => {
              try { await request(`/sermons/${sermon.id}`, { method: 'PATCH', body: { transcript: text } }); setEditing(false); onSaved(); }
              catch (e) { onError((e as Error).message); }
            }}>Save transcript</button>
            <button className="btn btn-ghost" onClick={() => { setText(sermon.transcript); setEditing(false); }}>Cancel</button>
          </div>
        </>
      ) : (
        <>
          <div className="transcript readonly">{sermon.transcript}</div>
          <div className="actions">
            <button className="btn btn-ghost" disabled={sermon.status === 'analyzing'} onClick={() => setEditing(true)}>Edit transcript</button>
            <button className="btn btn-ghost" onClick={() => navigator.clipboard.writeText(sermon.transcript)}>Copy</button>
            {canRetranscribe && <button className="btn btn-ghost" onClick={onRetranscribe}>Transcribe again</button>}
          </div>
        </>
      )}
    </>
  );
}

function AnalyzeForm({ sermon, minutes, model, disabled, onStart }: {
  sermon: Sermon; minutes: number; model?: string; disabled: boolean; onStart: (languages: Lang[], translate: boolean) => void;
}) {
  const [languages, setLanguages] = useState<Lang[]>(sermon.language === 'auto' ? ['en'] : [sermon.language]);
  const [translate, setTranslate] = useState(false);
  const translations = translate ? languages.filter((l) => l !== sermon.language).length : 0;
  return (
    <div className="analyze">
      <p className="muted">Claude ({model ?? 'claude-opus-5-5'}) writes a structured report: central message, summary, scriptures, main points, quotes, application, prayer points and small-group questions.</p>
      <fieldset>
        <legend>Report languages</legend>
        {ALL_LANGS.map((l) => (
          <label key={l} className="check">
            <input type="checkbox" checked={languages.includes(l)}
              onChange={(e) => setLanguages(e.target.checked ? [...languages, l] : languages.filter((x) => x !== l))} /> {LANGS[l]}
          </label>
        ))}
      </fieldset>
      <label className="check">
        <input type="checkbox" checked={translate} onChange={(e) => setTranslate(e.target.checked)} /> Also translate the full sermon text into these languages
      </label>
      <button className="btn btn-primary" disabled={disabled || !languages.length} onClick={() => onStart(languages, translate)}>
        {sermon.outputs.length ? 'Create again' : 'Create reports'}
      </button>
      <p className="muted small">Takes a few minutes. Estimated cost: about ${costHint(minutes, languages.length, false)}{translations ? ` + $${costHint(minutes, translations, false)} for translations` : ''}. Existing results in the same language are replaced.</p>
    </div>
  );
}

function Outputs({ sermon, onError }: { sermon: Sermon; onError: (m: string) => void }) {
  const reports = sermon.outputs.filter((o): o is Extract<Output, { kind: 'report' }> => o.kind === 'report');
  const [lang, setLang] = useState<Lang>(reports[0]?.language ?? 'en');
  const report = reports.find((r) => r.language === lang) ?? reports[0];
  const translation = sermon.outputs.find((o) => o.kind === 'translation' && o.language === report?.language);
  if (!report) return null;

  async function download(fmt: 'pdf' | 'md') {
    try { saveBlob(await fetchBlob(`/sermons/${sermon.id}/export/${report.language}.${fmt}`), `sermon-${sermon.sermon_date}-${report.language}.${fmt}`); }
    catch (e) { onError((e as Error).message); }
  }

  return (
    <div className="outputs">
      <div className="tabs" role="tablist">
        {reports.map((r) => (
          <button key={r.language} role="tab" aria-selected={r.language === report.language} className={r.language === report.language ? 'active' : ''}
            onClick={() => setLang(r.language)}>{LANGS[r.language]}</button>
        ))}
        <span className="spacer" />
        <button className="btn btn-small btn-ghost" onClick={() => download('pdf')}>⇩ PDF</button>
        <button className="btn btn-small btn-ghost" onClick={() => download('md')}>⇩ Markdown</button>
      </div>
      <ReportView report={report.content} />
      {translation && (
        <details className="translation">
          <summary>Full text ({LANGS[translation.language]})</summary>
          <div className="prose">{String(translation.content).split('\n\n').map((p, i) => <p key={i}>{p}</p>)}</div>
        </details>
      )}
      <p className="muted small">AI-generated from the transcript — please review before sharing.</p>
    </div>
  );
}

function ReportView({ report }: { report: Report }) {
  const list = (title: string, items: string[]) => items.length > 0 && (
    <section><h3>{title}</h3><ul>{items.map((x, i) => <li key={i}>{x}</li>)}</ul></section>
  );
  return (
    <article className="report prose">
      <h2>{report.title}</h2>
      <p className="central">{report.central_message}</p>
      {report.summary.split('\n\n').map((p, i) => <p key={i}>{p}</p>)}
      {report.scripture_references.length > 0 && (
        <section><h3>Scripture</h3><ul>{report.scripture_references.map((s, i) => <li key={i}><b>{s.reference}</b> — {s.context}</li>)}</ul></section>
      )}
      {report.main_points.length > 0 && (
        <section><h3>Main points</h3>
          <ol>{report.main_points.map((p, i) => (
            <li key={i}><b>{p.heading}</b>{p.scriptures.length > 0 && <span className="muted"> ({p.scriptures.join(', ')})</span>}<p>{p.explanation}</p></li>
          ))}</ol>
        </section>
      )}
      {report.key_quotes.length > 0 && <section><h3>Key quotes</h3>{report.key_quotes.map((q, i) => <blockquote key={i}>{q}</blockquote>)}</section>}
      {list('Application', report.applications)}
      {list('Prayer points', report.prayer_points)}
      {list('Discussion questions', report.discussion_questions)}
      {report.transcript_quality_note && <p className="muted small">Note on the transcript: {report.transcript_quality_note}</p>}
    </article>
  );
}
