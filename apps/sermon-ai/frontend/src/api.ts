export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
export const API = (import.meta.env.VITE_API_BASE || '/api/sermon-ai').replace(/\/$/, '');
export const PORTAL = import.meta.env.VITE_PORTAL_URL || '/';
export const PORTAL_ROOT = PORTAL.replace(/\/$/, '');

export type Lang = 'en' | 'fr' | 'de';
export const LANGS: Record<Lang, string> = { en: 'English', fr: 'Français', de: 'Deutsch' };
export type Status = 'recording' | 'recorded' | 'transcribing' | 'transcribed' | 'analyzing' | 'done';

export interface SermonSummary {
  id: string; title: string; preacher: string; sermon_date: string; language: 'auto' | Lang;
  status: Status; progress: string; error: string; duration_s: number; created_at: string;
  report_languages: string | null;
}
export interface Segment { idx: number; mime: string; bytes: number; complete: number; transcribed: number }
export interface Report {
  title: string; central_message: string; summary: string;
  scripture_references: { reference: string; context: string }[];
  main_points: { heading: string; explanation: string; scriptures: string[] }[];
  key_quotes: string[]; applications: string[]; prayer_points: string[]; discussion_questions: string[];
  transcript_quality_note: string;
}
export type Output =
  | { kind: 'report'; language: Lang; content: Report; model: string; created_at: string }
  | { kind: 'translation'; language: Lang; content: string; model: string; created_at: string };
export interface Sermon extends SermonSummary { transcript: string; segments: Segment[]; outputs: Output[] }
/** Signed-in CMGI account (cookie from the portal) or the legacy password session. */
export interface Me { name: string; email: string; is_admin: boolean; legacy: boolean; billed: boolean; ai_credit_seconds: number }
export interface ServiceStatus { transcription_configured: boolean; analysis_configured: boolean; claude_model: string; transcribe_model: string }

// localStorage (not sessionStorage) so a reloaded tab can still finish uploading a recording.
const TOKEN_KEY = 'sermon_ai_token';
export const auth = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* private mode */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } },
};

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = auth.get();
  const res = await fetch(API + path, {
    method: init.method || 'GET',
    headers: { ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = await res.json().catch(() => ({ detail: `Server error (${res.status})` }));
  if (!res.ok) {
    if (res.status === 401) { auth.clear(); window.dispatchEvent(new Event('sermon-auth')); }
    throw new ApiError(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail), res.status);
  }
  return data as T;
}

/** Authenticated binary download (audio playback, PDF/Markdown export). */
export async function fetchBlob(path: string): Promise<Blob> {
  const token = auth.get();
  const res = await fetch(API + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(`Download failed (${res.status})`, res.status);
  return res.blob();
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

export function formatDate(value: string) {
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : value;
}
