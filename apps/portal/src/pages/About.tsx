import { Icon } from '../components/Icon';
import { Link } from '../router';
import { PageHead } from './PageHead';

export function About() {
  return (
    <>
      <PageHead eyebrow="About" title="About CMGI Apps" text="A home for the digital tools that support our ministry, our events and our community." />
      <section className="section section-tight">
        <div className="container prose-grid">
          <div className="prose reveal">
            <h2>Why this platform exists</h2>
            <p>
              Ministry work produces many small, recurring tasks: registering guests, printing badges, welcoming people at the door,
              documenting sermons, sharing study material. CMGI Apps brings purpose-built tools for these tasks together under one
              address, with one consistent look and one place to find them.
            </p>
            <h2>How it is built</h2>
            <p>
              Every application is developed and deployed independently, so a new app never puts an existing one at risk.
              All apps run on our own server; data such as registrations and check-ins stays with us.
            </p>
            <h2>Where we are</h2>
            <p>
              <strong>EventPass Studio</strong> and <strong>Sermon Intelligence</strong> are available today, and a
              <strong> Bible Study</strong> app is planned. We will open each one here as soon as it is ready — not before.
            </p>
            <Link to="/apps" className="btn btn-primary">See all applications <Icon name="arrow" size={18} /></Link>
          </div>
          <aside className="fact-card reveal">
            <h3>At a glance</h3>
            <ul>
              <li><Icon name="grid" size={18} /> Independent apps, one platform</li>
              <li><Icon name="server" size={18} /> Self-hosted on our own server</li>
              <li><Icon name="lock" size={18} /> Role-based access per application</li>
              <li><Icon name="scan" size={18} /> Works on phones, tablets and desktops</li>
            </ul>
          </aside>
        </div>
      </section>
    </>
  );
}
