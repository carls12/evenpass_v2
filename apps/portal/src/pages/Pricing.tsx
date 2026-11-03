import { useEffect, useState } from 'react';
import { api, useAccount } from '../account';
import { Icon } from '../components/Icon';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

interface BillingConfig { enabled: boolean; pro: boolean; pro_label: string; packs: { minutes: number; label: string }[] }

const FREE = ['EventPass: create events, online registration', 'Body of Christ: Bible reading, personal goals, view progress', 'Sermon Intelligence: recordings and transcripts with your AI minutes'];
const PRO = ['EventPass: badge design & printing, QR check-in, gate staff', 'Body of Christ: all features incl. reports and printing', 'Free 14-day trial for every new account', 'Cancel any time in your account'];

/** Payment happens on Stripe's page; Pro or minutes are unlocked when Stripe confirms the payment. */
async function checkout(body: { product: 'pro' | 'minutes'; minutes?: number }) {
  const { url } = await api<{ url: string }>('/billing/checkout', { method: 'POST', body });
  window.location.assign(url);
}

export function Pricing() {
  const { account } = useAccount();
  const [config, setConfig] = useState<BillingConfig | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { api<BillingConfig>('/billing/config').then(setConfig, () => setConfig({ enabled: false, pro: false, pro_label: '', packs: [] })); }, []);

  async function buy(key: string, body: { product: 'pro' | 'minutes'; minutes?: number }) {
    if (!account) { navigate('/register?next=/pricing'); return; }
    setBusy(key); setError('');
    try { await checkout(body); } catch (err) { setError((err as Error).message); setBusy(''); }
  }
  const paidPro = account?.pro_source === 'subscription';

  return (
    <>
      <PageHead eyebrow="Plans" title="Simple plans for every ministry" text="Start free. Upgrade to Pro when you need badges, gate check-in and reports." />
      <section className="section section-tight">
        <div className="container">
          {error && <p className="banner banner-warn">{error}</p>}
          <div className="price-grid">
            <article className="price-card reveal">
              <h3>Free</h3>
              <p className="price">0 €</p>
              <p className="price-note">for everyone</p>
              <ul className="app-highlights">{FREE.map((i) => <li key={i}>{i}</li>)}</ul>
              {account ? <Link to="/account" className="btn btn-ghost app-cta">Your account</Link>
                : <Link to="/register" className="btn btn-primary app-cta">Create free account</Link>}
            </article>

            <article className="price-card reveal is-featured">
              <h3>Pro</h3>
              <p className="price">{config?.pro_label || 'Monthly'}</p>
              <p className="price-note">one subscription for all CMGI apps</p>
              <ul className="app-highlights">{PRO.map((i) => <li key={i}>{i}</li>)}</ul>
              {paidPro ? <Link to="/account" className="btn btn-ghost app-cta">You have Pro ✓</Link>
                : config?.pro ? (
                  <button className="btn btn-primary app-cta" disabled={busy === 'pro'} onClick={() => buy('pro', { product: 'pro' })}>
                    {busy === 'pro' ? 'Opening secure payment …' : account ? 'Get Pro' : 'Create account & get Pro'}
                  </button>
                ) : <span className="btn btn-disabled app-cta" aria-disabled="true">Online payment opens soon</span>}
            </article>

            <article className="price-card reveal">
              <h3>AI minutes</h3>
              <p className="price">Packages</p>
              <p className="price-note">for Sermon Intelligence — minutes never expire</p>
              <ul className="app-highlights"><li>Pay only for what you transcribe</li><li>5 free minutes to try it</li></ul>
              {config?.packs.length ? (
                <div className="pack-list">
                  {config.packs.map((p) => (
                    <button key={p.minutes} className="btn btn-ghost" disabled={busy === `m${p.minutes}`} onClick={() => buy(`m${p.minutes}`, { product: 'minutes', minutes: p.minutes })}>
                      <b>{p.minutes} min</b>{p.label && <span>{p.label}</span>}
                    </button>
                  ))}
                </div>
              ) : <span className="btn btn-disabled app-cta" aria-disabled="true">Online payment opens soon</span>}
            </article>
          </div>
          <p className="note reveal"><Icon name="lock" size={16} /> Secure payment by Stripe (card, SEPA, Apple Pay, Google Pay). Need help? Contact CMGI — the admin can also activate Pro for you.</p>
        </div>
      </section>
    </>
  );
}
