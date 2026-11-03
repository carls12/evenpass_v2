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
import './styles.css';

const ROUTES: Record<string, { title: string; page: () => JSX.Element | null }> = {
  '/': { title: 'CMGI Apps — Digital Solutions for Ministry and Community', page: Home },
  '/apps': { title: 'Applications · CMGI Apps', page: Apps },
  '/about': { title: 'About · CMGI Apps', page: About },
  '/contact': { title: 'Contact · CMGI Apps', page: Contact },
  '/login': { title: 'Sign in · CMGI Apps', page: () => <Login /> },
  '/register': { title: 'Create account · CMGI Apps', page: Register },
  '/forgot-password': { title: 'Forgot password · CMGI Apps', page: ForgotPassword },
  '/reset-password': { title: 'New password · CMGI Apps', page: ResetPassword },
  '/account': { title: 'My account · CMGI Apps', page: Account },
  '/admin': { title: 'Admin · CMGI Apps', page: Admin },
  '/pricing': { title: 'Plans · CMGI Apps', page: Pricing },
};

function NotFound() {
  return (
    <>
      <PageHead eyebrow="404" title="Page not found" text="This page does not exist (anymore)." />
      <section className="section section-tight"><div className="container"><Link to="/" className="btn btn-primary">Back to home</Link></div></section>
    </>
  );
}

function App() {
  const path = usePath();
  const route = ROUTES[path];
  useEffect(() => { document.title = route?.title ?? 'Not found · CMGI Apps'; }, [route]);
  const Page = route?.page ?? NotFound;
  return <Layout path={path}><Page /></Layout>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
