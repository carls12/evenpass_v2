import { useEffect, useState, type ReactNode } from 'react';
import { Link } from '../router';
import { SITE } from '../config/site';
import { Icon } from './Icon';

const NAV = [
  { to: '/', label: 'Home' },
  { to: '/apps', label: 'Applications' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
];

export function Layout({ path, children }: { path: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  useReveal(path);

  return (
    <>
      <header className={`site-header ${scrolled ? 'is-scrolled' : ''}`}>
        <div className="container header-inner">
          <Link to="/" className="brand" aria-label="CMGI Apps home">
            <img src="/cmgi-logo.png" alt="" width={40} height={40} />
            <span>CMGI <b>Apps</b></span>
          </Link>
          <nav className={`main-nav ${open ? 'is-open' : ''}`} aria-label="Main">
            {NAV.map((n) => (
              <Link key={n.to} to={n.to} className={path === n.to ? 'active' : ''} aria-current={path === n.to ? 'page' : undefined}>
                {n.label}
              </Link>
            ))}
            <Link to="/login" className={`btn btn-primary btn-small nav-login ${path === '/login' ? 'active' : ''}`}>
              <Icon name="lock" size={16} /> Login
            </Link>
          </nav>
          <button className="menu-toggle" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} onClick={() => setOpen(!open)}>
            <Icon name={open ? 'close' : 'menu'} />
          </button>
        </div>
      </header>
      <main id="content">{children}</main>
      <footer className="site-footer">
        <div className="container footer-inner">
          <div className="brand brand-footer">
            <img src="/cmgi-logo.png" alt="" width={32} height={32} />
            <span>CMGI <b>Apps</b></span>
          </div>
          <p>One platform. Multiple applications. One mission.</p>
          <nav aria-label="Footer">
            {NAV.slice(1).map((n) => <Link key={n.to} to={n.to}>{n.label}</Link>)}
          </nav>
          <small>© {new Date().getFullYear()} {SITE.organisation}</small>
        </div>
      </footer>
    </>
  );
}

/** Fades elements with .reveal in as they scroll into view (skipped for reduced motion). */
function useReveal(path: string) {
  useEffect(() => {
    const items = document.querySelectorAll<HTMLElement>('.reveal:not(.is-visible)');
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add('is-visible'); io.unobserve(e.target); }
    }), { threshold: 0.12 });
    items.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [path]);
}
