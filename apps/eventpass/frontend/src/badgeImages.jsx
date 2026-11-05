import { useEffect, useRef, useState } from 'react';

// Picture for the badge of one event: shows what is used now, change it any time,
// or go back to the standard picture / CMGI logo.
export function BadgeImagePicker({ label, kind, src, fallback, version, onUpload, onReset }) {
  const input = useRef(null);
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setCustom(false); }, [src, version]);

  async function pick(file) {
    if (!file) return;
    setBusy(true);
    try { await onUpload(file, kind); } finally {
      setBusy(false);
      if (input.current) input.current.value = ''; // the same file can be chosen again
    }
  }
  async function reset() {
    setBusy(true);
    try { await onReset(kind); } finally { setBusy(false); }
  }

  return (
    <div className="image-picker">
      <span className="image-picker-label">{label}</span>
      <div className="image-picker-row">
        <img key={`${src}-${version}`} className={`image-picker-thumb ${kind}`} alt=""
          src={`${src}?v=${version}`} onLoad={(e) => setCustom(e.currentTarget.src.includes('/badge-image/'))}
          onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = fallback; setCustom(false); }} />
        <div>
          <small className="hint">{custom ? 'Eigenes Bild für dieses Event' : kind === 'logo' ? 'Standard: CMGI-Logo' : 'Standardbild (Demo)'}</small>
          <div className="actions">
            <button type="button" className="secondary small" disabled={busy} onClick={() => input.current?.click()}>
              {busy ? 'Bitte warten …' : custom ? 'Bild ändern' : 'Eigenes Bild hochladen'}
            </button>
            {custom && <button type="button" className="secondary small" disabled={busy} onClick={reset}>
              {kind === 'logo' ? 'CMGI-Logo verwenden' : 'Standardbild verwenden'}
            </button>}
          </div>
        </div>
      </div>
      <input ref={input} type="file" hidden accept="image/png,image/jpeg,image/webp" onChange={(e) => pick(e.target.files?.[0])} />
    </div>
  );
}
