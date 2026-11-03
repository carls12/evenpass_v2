import { useEffect, useState } from 'react';

// Central CMGI account. The session is an httpOnly cookie for the whole domain, so signing in
// here also signs you in to EventPass, Sermon Intelligence and Body of Christ.

export interface Account {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  is_admin: boolean;
  created_at: string;
  pro: boolean;
  pro_source: 'trial' | 'subscription' | 'grant' | null;
  pro_until: string | null;
  trial_ends_at: string | null;
  trial_used: boolean;
  subscription: { status: string; current_period_end: string | null } | null;
  ai_credit_seconds: number;
}

/** Inside the CMGI mobile app (Capacitor adds this to the user agent). Store rules: no purchases in the app. */
export const IN_APP = typeof navigator !== 'undefined' && navigator.userAgent.includes('CMGIApp');

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api/accounts${path}`, {
    method: init.method ?? 'GET',
    credentials: 'same-origin',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? 'Please check your input.'
      : res.status >= 500 ? 'The service is not reachable right now. Please try again shortly.' : 'Something went wrong.';
    throw new ApiError(message, res.status);
  }
  return data as T;
}

// A tiny shared store: every component sees the same account state.
type State = { account: Account | null; loading: boolean };
let state: State = { account: null, loading: true };
const listeners = new Set<() => void>();
function set(next: Partial<State>) { state = { ...state, ...next }; listeners.forEach((fn) => fn()); }

export async function refreshAccount() {
  try { set({ account: await api<Account>('/me'), loading: false }); }
  catch { set({ account: null, loading: false }); }
}

export function setAccount(account: Account | null) { set({ account, loading: false }); }

export async function signOut() {
  await api('/logout', { method: 'POST' }).catch(() => undefined);
  set({ account: null, loading: false });
}

let started = false;
export function useAccount() {
  const [snapshot, setSnapshot] = useState(state);
  useEffect(() => {
    const update = () => setSnapshot(state);
    listeners.add(update);
    if (!started) { started = true; refreshAccount(); }
    update();
    return () => { listeners.delete(update); };
  }, []);
  return snapshot;
}

export function daysLeft(iso: string | null) {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000));
}

export function minutes(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m} min ${s} s` : `${m} min`;
}

export function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
}

/** Where to continue after signing in: only paths on this site (no open redirects). */
export function nextPath(fallback = '/account') {
  const next = new URLSearchParams(window.location.search).get('next') || '';
  return next.startsWith('/') && !next.startsWith('//') ? next : fallback;
}
