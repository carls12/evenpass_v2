import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { en, type Key } from './en';
import { fr } from './fr';
import { de } from './de';
import { es } from './es';
import { pt } from './pt';

// Languages of the portal and of every CMGI app. The choice is a cookie for the whole site
// (cmgi_lang, path /), so EventPass, Sermon Intelligence and Body of Christ follow it too.
// First visit: the browser's language; anything we do not have falls back to English.

export const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
  { code: 'pt', label: 'Português' },
] as const;
export type Lang = (typeof LANGS)[number]['code'];

const MESSAGES: Record<Lang, Record<Key, string>> = { en, fr, de, es, pt };
const COOKIE = 'cmgi_lang';

function isLang(value: string | undefined | null): value is Lang {
  return !!value && LANGS.some((l) => l.code === value);
}

export function detectLang(): Lang {
  const saved = document.cookie.split('; ').find((c) => c.startsWith(`${COOKIE}=`))?.split('=')[1];
  if (isLang(saved)) return saved;
  for (const tag of navigator.languages ?? [navigator.language]) {
    const base = tag?.slice(0, 2).toLowerCase();
    if (isLang(base)) return base;
  }
  return 'en';
}

let lang: Lang = detectLang();
document.documentElement.lang = lang;
const listeners = new Set<() => void>();

export function setLang(next: Lang) {
  lang = next;
  document.cookie = `${COOKIE}=${next}; path=/; max-age=31536000; SameSite=Lax`;
  document.documentElement.lang = next;
  listeners.forEach((fn) => fn());
}

export function currentLang() { return lang; }

/** Translated text; {name} placeholders are filled from vars. */
export function t(key: Key, vars: Record<string, string | number> = {}) {
  const text = MESSAGES[lang][key] ?? en[key];
  return text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`));
}

/** Like t(), but placeholders may be React elements (e.g. a bold email address or a link). */
export function tx(key: Key, vars: Record<string, ReactNode>) {
  const text = MESSAGES[lang][key] ?? en[key];
  return text.split(/(\{\w+\})/).map((part, i) => {
    const name = part.match(/^\{(\w+)\}$/)?.[1];
    return <Fragment key={i}>{name && name in vars ? vars[name] : part}</Fragment>;
  });
}

/** Backend messages are English; known ones are shown in the user's language. */
const SERVER_MESSAGES: Record<string, Key> = {
  'Email or password is incorrect': 'err.badLogin',
  'An account with this email already exists. Please sign in.': 'err.exists',
  'Please enter a valid email address': 'err.email',
  'Too many attempts. Please wait 15 minutes.': 'err.throttle',
  'This link is invalid or has expired. Please request a new one.': 'err.link',
  'Current password is incorrect': 'err.currentPassword',
  'You already have a Pro subscription. Manage it in your account.': 'err.hasPro',
  'Online payment is not set up yet.': 'err.noPayment',
  'Pro is not on sale online yet.': 'err.noPayment',
  'This account has been deactivated. Please contact CMGI.': 'err.disabled',
  'Request from another website refused': 'err.origin',
  'Please check your input.': 'err.input',
  'The service is not reachable right now. Please try again shortly.': 'err.offline',
  'Something went wrong.': 'err.generic',
  'This join link is not valid (anymore)': 'err.joinLink',
  'All places of this organisation are taken. Please contact its admin.': 'err.full',
  'This address is already taken': 'err.slugTaken',
  'This address is reserved': 'err.slugReserved',
  'An organisation needs at least one admin': 'err.lastAdmin',
};
export function tError(message: string) {
  const key = SERVER_MESSAGES[message];
  return key ? t(key) : message;
}

/** Re-renders the component when the language changes. */
export function useLang() {
  const [, force] = useState(0);
  useEffect(() => {
    const update = () => force((n) => n + 1);
    listeners.add(update);
    return () => { listeners.delete(update); };
  }, []);
  return lang;
}

export function LanguageSwitcher() {
  const active = useLang();
  return (
    <label className="lang-switch">
      <span className="sr-only">{t('nav.language')}</span>
      <select value={active} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t('nav.language')}>
        {LANGS.map((l) => <option key={l.code} value={l.code}>{l.code.toUpperCase()} · {l.label}</option>)}
      </select>
    </label>
  );
}
