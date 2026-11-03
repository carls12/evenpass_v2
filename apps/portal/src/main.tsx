import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { Layout } from './components/Layout';
import { Link, usePath } from './router';
import { Home } from './pages/Home';
import { Apps } from './pages/Apps';
import { About } from './pages/About';
import { Contact } from './pages/Contact';
import { ForgotPassword, Login, Register, ResetPassword } from './pages/Login';
import { Account } from './pages/Account';
import { Admin } from './pages/Admin';
import { Pricing } from './pages/Pricing';
import { PageHead } from './pages/PageHead';
import { OrgPage } from './pages/OrgPage';
import { t, useLang } from './i18n';
import type { Key } from './i18n/en';
import './styles.css';

const ROUTES: Record<string, { title: Key; page: () => JSX.Element | null }> = {
  '/': { title: 'title.home', page: Home },
  '/apps': { title: 'title.apps', page: Apps },
  '/about': { title: 'title.about', page: About },
  '/contact': { title: 'title.contact', page: Contact },
  '/login': { title: 'title.login', page: () => <Login /> },
  '/register': { title: 'title.register', page: Register },
  '/forgot-password': { title: 'title.forgot', page: ForgotPassword },
  '/reset-password': { title: 'title.reset', page: ResetPassword },
  '/account': { title: 'title.account', page: Account },
  '/admin': { title: 'title.admin', page: Admin },
  '/pricing': { title: 'title.pricing', page: Pricing },
};

function pageTitle(key: Key) { return key === 'title.home' ? t(key) : `${t(key)} · CMGI Apps`; }

function NotFound() {
  return (
    <>
      <PageHead eyebrow="404" title={t('notFound.title')} text={t('notFound.text')} />
      <section className="section section-tight"><div className="container"><Link to="/" className="btn btn-primary">{t('notFound.back')}</Link></div></section>
    </>
  );
}

function App() {
  const path = usePath();
  const lang = useLang(); // the whole page re-renders in the new language
  const route = ROUTES[path];
  // Any other one-part address may be the page of a church or ministry (cmgi-apps.de/icc).
  const orgSlug = !route && /^\/[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$/.test(path) ? path.slice(1) : null;
  useEffect(() => { if (!orgSlug) document.title = pageTitle(route?.title ?? 'title.notFound'); }, [route, lang, orgSlug]);
  if (orgSlug) return <Layout path={path}><OrgPage key={orgSlug} slug={orgSlug} /></Layout>;
  const Page = route?.page ?? NotFound;
  return <Layout path={path}><Page /></Layout>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
