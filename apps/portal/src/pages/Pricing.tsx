import { useAccount } from '../account';
import { Icon } from '../components/Icon';
import { Link } from '../router';
import { PageHead } from './PageHead';

// Online payment (Stripe) is the next phase. Until then this page shows the plans honestly
// and Pro is given by the CMGI admin.
const PLANS = [
  {
    name: 'Free', price: '0 €', note: 'for everyone',
    items: ['EventPass: create events, online registration', 'Body of Christ: Bible reading, personal goals, view progress', 'Sermon Intelligence: recordings and transcripts with your AI minutes'],
  },
  {
    name: 'Pro', price: 'Monthly', note: 'one subscription for all CMGI apps', highlight: true,
    items: ['EventPass: badge design & printing, QR check-in, gate staff', 'Body of Christ: all features incl. reports and printing', 'Free 14-day trial for every new account'],
  },
  {
    name: 'AI minutes', price: 'Packages', note: 'for Sermon Intelligence',
    items: ['Pay only for what you transcribe', '5 free minutes to try it', 'Minutes never expire'],
  },
];

export function Pricing() {
  const { account } = useAccount();
  return (
    <>
      <PageHead eyebrow="Plans" title="Simple plans for every ministry" text="Start free. Upgrade to Pro when you need badges, gate check-in and reports." />
      <section className="section section-tight">
        <div className="container">
          <div className="price-grid">
            {PLANS.map((p) => (
              <article key={p.name} className={`price-card reveal ${p.highlight ? 'is-featured' : ''}`}>
                <h3>{p.name}</h3>
                <p className="price">{p.price}</p>
                <p className="price-note">{p.note}</p>
                <ul className="app-highlights">{p.items.map((i) => <li key={i}>{i}</li>)}</ul>
                {p.name === 'Free' ? (
                  account ? <Link to="/account" className="btn btn-ghost app-cta">Your account</Link>
                    : <Link to="/register" className="btn btn-primary app-cta">Create free account</Link>
                ) : (
                  <span className="btn btn-disabled app-cta" aria-disabled="true">Online payment opens soon</span>
                )}
              </article>
            ))}
          </div>
          <p className="note reveal"><Icon name="mail" size={16} /> Need Pro or AI minutes now? Contact CMGI — the admin can activate it for your account right away.</p>
        </div>
      </section>
    </>
  );
}
