import { Icon, type IconName } from '../components/Icon';
import { PageHead } from './PageHead';

// There is no central CMGI account system yet. Instead of a login form that would not
// work, this page sends people to the sign-in that actually exists in each app.
const ENTRIES: { icon: IconName; title: string; text: string; href: string; cta: string }[] = [
  { icon: 'ticket', title: 'EventPass — Administration', text: 'Create events, design badges, manage participants and gate staff.', href: '/eventpass/', cta: 'Admin sign-in' },
  { icon: 'waveform', title: 'Sermon Intelligence', text: 'Record sermons and create transcripts, reports and translations.', href: '/sermon-ai/', cta: 'Sign in' },
  { icon: 'scan', title: 'EventPass — Gate team', text: 'Sign in with the temporary access you received for an event to check guests in.', href: '/eventpass/gate', cta: 'Gate sign-in' },
];

export function Login() {
  return (
    <>
      <PageHead eyebrow="Login" title="Sign in" text="Choose the application you want to access." />
      <section className="section section-tight">
        <div className="container">
          <div className="login-grid">
            {ENTRIES.map((e) => (
              <a className="login-card reveal" href={e.href} key={e.href}>
                <span className="pillar-icon"><Icon name={e.icon} /></span>
                <div>
                  <h3>{e.title}</h3>
                  <p>{e.text}</p>
                  <span className="link-arrow">{e.cta} <Icon name="arrow" size={16} /></span>
                </div>
              </a>
            ))}
          </div>
          <p className="note reveal">
            <Icon name="lock" size={16} /> A single CMGI Apps account for all applications is planned. Until then, each application has its own sign-in.
          </p>
        </div>
      </section>
    </>
  );
}
