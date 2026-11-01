import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from 'react';
import { BASE } from './api';

// ---------------------------------------------------------------- tiny router (paths relative to BASE)

const listeners = new Set<() => void>();
const appPath = () => {
  const p = window.location.pathname;
  return (p.startsWith(BASE) ? p.slice(BASE.length) : p).replace(/\/+$/, '') || '/';
};
export function navigate(to: string) {
  window.history.pushState({}, '', BASE + to);
  listeners.forEach((fn) => fn());
  window.scrollTo({ top: 0 });
}
export function usePath() {
  const [path, setPath] = useState(appPath());
  useEffect(() => {
    const update = () => setPath(appPath());
    listeners.add(update);
    window.addEventListener('popstate', update);
    return () => { listeners.delete(update); window.removeEventListener('popstate', update); };
  }, []);
  return path;
}
export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    navigate(to);
  };
  return <a href={BASE + to} onClick={handle} {...rest} />;
}

