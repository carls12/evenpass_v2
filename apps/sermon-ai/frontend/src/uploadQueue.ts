import { API, auth } from './api';

/**
 * Durable, ordered upload queue for recordings.
 *
 * Every recorder chunk is written to IndexedDB first and only removed after the server
 * confirmed it. A dropped connection, a reload or a crashed tab therefore loses nothing:
 * the queue resumes on the next page load and keeps the original order.
 */
export type QueueItem =
  | { key?: number; sermonId: string; kind: 'chunk'; segment: number; seq: number; mime: string; blob: Blob }
  | { key?: number; sermonId: string; kind: 'complete'; segment: number }
  | { key?: number; sermonId: string; kind: 'finish'; duration: number };

export interface QueueState { pending: number; pendingBySermon: Record<string, number>; offline: boolean; needsLogin: boolean; error: string }

const DB_NAME = 'sermon-ai-uploads';
const STORE = 'queue';
let dbPromise: Promise<IDBDatabase | null> | null = null;
const memory: QueueItem[] = []; // fallback when IndexedDB is unavailable (e.g. some private modes)
let memoryKey = 0;

function openDb(): Promise<IDBDatabase | null> {
  dbPromise ??= new Promise((resolve) => {
    try {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'key', autoIncrement: true });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return dbPromise;
}

function tx<T>(db: IDBDatabase, mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const r = run(db.transaction(STORE, mode).objectStore(STORE));
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

async function all(): Promise<QueueItem[]> {
  const db = await openDb();
  return db ? tx(db, 'readonly', (s) => s.getAll() as IDBRequest<QueueItem[]>) : [...memory];
}

async function remove(key: number) {
  const db = await openDb();
  if (db) await tx(db, 'readwrite', (s) => s.delete(key));
  else memory.splice(memory.findIndex((i) => i.key === key), 1);
}

export async function enqueue(item: QueueItem) {
  const db = await openDb();
  if (db) await tx(db, 'readwrite', (s) => s.add(item));
  else memory.push({ ...item, key: ++memoryKey });
  await publish();
  void pump();
}

/** Highest segment number still waiting locally for a sermon (so a resumed recording continues after it). */
export async function maxQueuedSegment(sermonId: string): Promise<number> {
  const items = await all();
  return Math.max(-1, ...items.filter((i) => i.sermonId === sermonId && i.kind !== 'finish').map((i) => ('segment' in i ? i.segment : -1)));
}

// ---------------------------------------------------------------- state & listeners

let state: QueueState = { pending: 0, pendingBySermon: {}, offline: !navigator.onLine, needsLogin: false, error: '' };
const listeners = new Set<(s: QueueState) => void>();

export function subscribe(fn: (s: QueueState) => void) {
  listeners.add(fn);
  fn(state);
  return () => { listeners.delete(fn); };
}

async function publish(patch: Partial<QueueState> = {}) {
  const items = await all();
  const pendingBySermon: Record<string, number> = {};
  items.forEach((i) => { pendingBySermon[i.sermonId] = (pendingBySermon[i.sermonId] || 0) + 1; });
  state = { ...state, ...patch, pending: items.length, pendingBySermon };
  listeners.forEach((fn) => fn(state));
}

// ---------------------------------------------------------------- sending

class Retry extends Error {}

async function send(item: QueueItem) {
  const token = auth.get();  // legacy password session; otherwise the CMGI cookie is sent automatically
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  let res: Response;
  try {
    if (item.kind === 'chunk') {
      res = await fetch(`${API}/sermons/${item.sermonId}/segments/${item.segment}/chunks/${item.seq}`,
        { method: 'PUT', headers: { ...headers, 'Content-Type': item.mime }, body: item.blob });
    } else if (item.kind === 'complete') {
      res = await fetch(`${API}/sermons/${item.sermonId}/segments/${item.segment}/complete`, { method: 'POST', headers });
    } else {
      res = await fetch(`${API}/sermons/${item.sermonId}/finish`,
        { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ duration_s: item.duration }) });
    }
  } catch {
    throw new Retry('offline');
  }
  if (res.ok) return;
  if (res.status === 401) throw new Retry('login');
  if (res.status >= 500 || res.status === 429 || res.status === 408) throw new Retry('server');
  // 404 (sermon deleted), 409/413/415/422: the server will never accept this item — drop it, but say so.
  const detail = await res.json().then((d) => d.detail).catch(() => res.statusText);
  await publish({ error: `An upload was rejected: ${detail}` });
}

let running = false;
let delay = 1000;

export async function pump() {
  if (running) return;
  running = true;
  try {
    for (;;) {
      const items = await all();
      if (!items.length) { delay = 1000; await publish({ offline: false, needsLogin: false }); return; }
      const next = items.sort((a, b) => (a.key ?? 0) - (b.key ?? 0))[0];
      try {
        await send(next);
        await remove(next.key!);
        delay = 1000;
        await publish({ offline: false, needsLogin: false });
      } catch (e) {
        if (!(e instanceof Retry)) throw e;
        if (e.message === 'login') { await publish({ needsLogin: true }); return; } // resumes after the next login
        await publish({ offline: e.message === 'offline' });
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, 30000);
      }
    }
  } finally {
    running = false;
  }
}

window.addEventListener('online', () => void pump());
void publish().then(() => pump());
