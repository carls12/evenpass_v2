// Continuous QR scanner shared by the admin page and the gate app.
// The library is loaded on demand, keeping the registration page light on phones.
// A badge held in front of the camera is checked once; it counts again only after being out of view this long.
const SAME_CODE_PAUSE_MS = 3000;

export async function startQrScanner(elementId, onCode) {
  const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode');
  const qr = new Html5Qrcode(elementId, {
    formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
    useBarCodeDetectorIfSupported: true, // native, faster decoder on Android/Chrome when available
    verbose: false,
  });
  let busy = false, last = '', lastAt = 0;
  await qr.start(
    { facingMode: 'environment' },
    { fps: 12, qrbox: (w, h) => { const s = Math.max(50, Math.floor(Math.min(w, h) * 0.75)); return { width: s, height: s }; } },
    async text => {
      const value = text.trim();
      if (value === last && Date.now() - lastAt < SAME_CODE_PAUSE_MS) { lastAt = Date.now(); return; }
      if (busy) return;
      busy = true; last = value; lastAt = Date.now();
      try { await onCode(value); } finally { busy = false; lastAt = Date.now(); }
    },
    () => {},
  );
  return () => qr.stop().then(() => qr.clear()).catch(() => {});
}

export function cameraError(e) {
  const name = e?.name || '';
  if (name === 'NotAllowedError' || /permission/i.test(String(e))) return 'Kamerazugriff wurde abgelehnt. Bitte in den Browser-Einstellungen erlauben.';
  if (!window.isSecureContext) return 'Kamera nur über HTTPS (oder localhost) verfügbar.';
  if (name === 'NotFoundError') return 'Keine Kamera gefunden.';
  return 'Kamera konnte nicht gestartet werden: ' + (e?.message || e);
}

// Short tone + vibration so the gate team does not have to look at the screen for every guest.
let audio;
export function feedback(status) {
  try {
    navigator.vibrate?.(status === 'checked_in' ? 120 : [80, 60, 80]);
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.frequency.value = status === 'checked_in' ? 880 : status === 'duplicate' ? 520 : 220;
    gain.gain.setValueAtTime(0.15, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.25);
    osc.connect(gain).connect(audio.destination);
    osc.start(); osc.stop(audio.currentTime + 0.25);
  } catch {}
}
