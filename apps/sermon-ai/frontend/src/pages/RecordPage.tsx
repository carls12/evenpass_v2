import { useEffect, useRef, useState } from 'react';
import { formatDate, formatDuration, request, type Sermon } from '../api';
import { enqueue, maxQueuedSegment } from '../uploadQueue';
import { pickMimeType, SegmentedRecorder } from '../recorder';
import { Link, navigate } from '../router';
import { useQueue } from '../useQueue';

type Phase = 'idle' | 'starting' | 'recording' | 'stopping';

export function RecordPage({ id }: { id: string }) {
  const [sermon, setSermon] = useState<Sermon | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState('');
  const [wakeLock, setWakeLock] = useState<'on' | 'unsupported' | 'off'>('off');
  const queue = useQueue();
  const recorder = useRef<SegmentedRecorder | null>(null);
  const startedAt = useRef(0);
  const cleanup = useRef<() => void>(() => {});
  const mime = pickMimeType();
  const pending = queue?.pendingBySermon[id] ?? 0;

  useEffect(() => { request<Sermon>(`/sermons/${id}`).then(setSermon).catch((e) => setError(e.message)); }, [id]);

  // Warn before closing the tab while recording or while audio still waits on this device.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (phase === 'recording' || pending > 0) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [phase, pending]);

  useEffect(() => () => cleanup.current(), []);

  async function start() {
    if (!sermon) return;
    setError('');
    if (!mime) { setError('This browser cannot record audio. Please use a current Chrome, Edge, Firefox or Safari.'); return; }
    setPhase('starting');
    try {
      let first = Math.max(-1, ...sermon.segments.map((s) => s.idx), await maxQueuedSegment(id)) + 1;
      if (sermon.status === 'recorded') first = Math.max(first, (await request<{ next_segment: number }>(`/sermons/${id}/resume`, { method: 'POST' })).next_segment);
      else if (sermon.status !== 'recording') throw new Error('This sermon has already been transcribed.');

      // Natural room sound for a preacher at a distance: no echo cancellation or noise suppression.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
      const rec = new SegmentedRecorder(
        stream, mime,
        (segment, seq, blob) => void enqueue({ sermonId: id, kind: 'chunk', segment, seq, mime: mime.split(';')[0], blob }),
        (segment) => void enqueue({ sermonId: id, kind: 'complete', segment }),
        (message) => setError(message),
      );
      rec.start(first);
      recorder.current = rec;
      startedAt.current = Date.now();
      setPhase('recording');
      cleanup.current = monitor(stream);
    } catch (e) {
      setPhase('idle');
      const err = e as Error;
      setError(err.name === 'NotAllowedError'
        ? 'Microphone access was blocked. Allow the microphone for this site in the browser settings and try again.'
        : err.message);
    }
  }

  /** Timer, level meter and screen wake lock while recording. */
  function monitor(stream: MediaStream) {
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt.current) / 1000)), 500);
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
      setLevel(Math.min(1, peak / 90));
      frame = requestAnimationFrame(tick);
    };
    tick();

    let lock: WakeLockSentinel | null = null;
    const acquire = async () => {
      if (!('wakeLock' in navigator)) { setWakeLock('unsupported'); return; }
      try { lock = await navigator.wakeLock.request('screen'); setWakeLock('on'); } catch { setWakeLock('off'); }
    };
    const onVisible = () => { if (document.visibilityState === 'visible') void acquire(); };
    void acquire();
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(timer);
      cancelAnimationFrame(frame);
      void ctx.close();
      document.removeEventListener('visibilitychange', onVisible);
      void lock?.release();
      setWakeLock('off');
    };
  }

  async function stop() {
    if (!recorder.current || !sermon) return;
    setPhase('stopping');
    await recorder.current.stop();
    recorder.current = null;
    cleanup.current();
    cleanup.current = () => {};
    const total = sermon.duration_s + Math.floor((Date.now() - startedAt.current) / 1000);
    await enqueue({ sermonId: id, kind: 'finish', duration: total });
    navigate(`/sermons/${id}`);
  }

  if (!sermon) return <main className="container narrow">{error ? <p className="alert error">{error}</p> : <p className="muted">Loading…</p>}</main>;

  const recording = phase === 'recording';
  return (
    <main className="container narrow">
      <Link to={`/sermons/${id}`} className="back">← {sermon.title}</Link>
      <section className={`card recorder ${recording ? 'is-recording' : ''}`}>
        <p className="muted small">{formatDate(sermon.sermon_date)}{sermon.preacher && ` · ${sermon.preacher}`}</p>
        <h1>{sermon.title}</h1>

        <div className="rec-time" aria-live="off">{formatDuration(recording || phase === 'stopping' ? elapsed : 0)}</div>
        <div className="meter" aria-hidden="true"><span style={{ transform: `scaleX(${recording ? level : 0})` }} /></div>

        {phase === 'idle' || phase === 'starting' ? (
          <button className="rec-button" onClick={start} disabled={phase === 'starting'} aria-label="Start recording">
            <span className="dot" /> {sermon.segments.length || sermon.status === 'recorded' ? 'Record more' : 'Start recording'}
          </button>
        ) : (
          <button className="rec-button stop" onClick={stop} disabled={phase === 'stopping'} aria-label="Stop recording">
            <span className="square" /> {phase === 'stopping' ? 'Saving…' : 'Stop & finish'}
          </button>
        )}

        {error && <p className="alert error">{error}</p>}

        <ul className="rec-status">
          <li className={pending === 0 ? 'ok' : queue?.offline ? 'warn' : 'busy'}>
            {pending === 0 ? 'Everything is saved on the server' : queue?.offline
              ? `No connection — ${pending} part(s) safely stored on this device, upload resumes automatically`
              : `Uploading… ${pending} part(s) waiting`}
          </li>
          {recording && <li className={wakeLock === 'on' ? 'ok' : 'warn'}>
            {wakeLock === 'on' ? 'Screen stays on while recording' : 'Keep this screen on — the device may stop recording when it locks'}
          </li>}
        </ul>
      </section>

      <section className="tips">
        <h2>Tips for a good recording</h2>
        <ul>
          <li>Place the phone or laptop close to a loudspeaker or the pulpit, and plug in the charger.</li>
          <li>Keep this page open in the foreground. Switching apps can pause recording on phones.</li>
          <li>If something goes wrong, open this sermon again and press <b>Record more</b> — nothing recorded so far is lost.</li>
        </ul>
      </section>
    </main>
  );
}
