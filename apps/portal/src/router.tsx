import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from 'react';

// Minimal history router for the portal's handful of pages. Links to other apps
// (e.g. /eventpass/) are ordinary page loads because each app is a separate build.

const listeners = new Set<() => void>();

export function navigate(to: string) {
  window.history.pushState({}, '', to);
  listeners.forEach((fn) => fn());
  window.scrollTo({ top: 0 });
}

export function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    listeners.add(update);
    window.addEventListener('popstate', update);
    return () => {
      listeners.delete(update);
      window.removeEventListener('popstate', update);
    };
  }, []);
  return path.replace(/\/+$/, '') || '/';
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string };

export function Link({ to, onClick, ...rest }: LinkProps) {
  function handle(e: MouseEvent<HTMLAnchorElement>) {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
  }
  return <a href={to} onClick={handle} {...rest} />;
}
