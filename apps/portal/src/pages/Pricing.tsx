import { useEffect, useState } from 'react';
import { api, IN_APP, useAccount } from '../account';
import { Icon } from '../components/Icon';
import { t, tError } from '../i18n';
import type { Key } from '../i18n/en';
import { Link, navigate } from '../router';
import { PageHead } from './PageHead';

interface BillingConfig { enabled: boolean; pro: boolean; pro_label: string; packs: { minutes: number; label: string }[] }

const FREE: Key[] = ['pricing.free1', 'pricing.free2', 'pricing.free3'];
const PRO: Key[] = ['pricing.pro1', 'pricing.pro2', 'pricing.pro3', 'pricing.pro4'];

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
    try { await checkout(body); } catch (err) { setError(tError((err as Error).message)); setBusy(''); }
  }
  const paidPro = account?.pro_source === 'subscription';
  const unavailable = <span className="btn btn-disabled app-cta" aria-disabled="true">{IN_APP ? t('pricing.onWebsite') : t('pricing.soon')}</span>;

  return (
    <>
      <PageHead eyebrow={t('pricing.eyebrow')} title={t('pricing.title')} text={t('pricing.text')} />
      <section className="section section-tight">
        <div className="container">
          {error && <p className="banner banner-warn">{error}</p>}
          {IN_APP && <p className="banner banner-ok">{t('pricing.inApp')}</p>}
          <div className="price-grid">
            <article className="price-card reveal">
              <h3>{t('pricing.free')}</h3>
              <p className="price">0 €</p>
              <p className="price-note">{t('pricing.forEveryone')}</p>
              <ul className="app-highlights">{FREE.map((i) => <li key={i}>{t(i)}</li>)}</ul>
              {account ? <Link to="/account" className="btn btn-ghost app-cta">{t('pricing.yourAccount')}</Link>
                : <Link to="/register" className="btn btn-primary app-cta">{t('pricing.createFree')}</Link>}
            </article>

            <article className="price-card reveal is-featured">
              <h3>Pro</h3>
              <p className="price">{config?.pro_label || t('pricing.monthly')}</p>
              <p className="price-note">{t('pricing.oneSubscription')}</p>
              <ul className="app-highlights">{PRO.map((i) => <li key={i}>{t(i)}</li>)}</ul>
              {paidPro ? <Link to="/account" className="btn btn-ghost app-cta">{t('pricing.havePro')}</Link>
                : config?.pro && !IN_APP ? (
                  <button className="btn btn-primary app-cta" disabled={busy === 'pro'} onClick={() => buy('pro', { product: 'pro' })}>
                    {busy === 'pro' ? t('pricing.opening') : account ? t('pricing.getPro') : t('pricing.createAndGetPro')}
                  </button>
                ) : unavailable}
            </article>

            <article className="price-card reveal">
              <h3>{t('pricing.minutes')}</h3>
              <p className="price">{t('pricing.packages')}</p>
              <p className="price-note">{t('pricing.minutesNote')}</p>
              <ul className="app-highlights"><li>{t('pricing.m1')}</li><li>{t('pricing.m2')}</li></ul>
              {config?.packs.length && !IN_APP ? (
                <div className="pack-list">
                  {config.packs.map((p) => (
                    <button key={p.minutes} className="btn btn-ghost" disabled={busy === `m${p.minutes}`} onClick={() => buy(`m${p.minutes}`, { product: 'minutes', minutes: p.minutes })}>
                      <b>{t('pricing.min', { n: p.minutes })}</b>{p.label && <span>{p.label}</span>}
                    </button>
                  ))}
                </div>
              ) : unavailable}
            </article>
          </div>
          <p className="note reveal"><Icon name="lock" size={16} /> {t('pricing.secure')}</p>
        </div>
      </section>
    </>
  );
}
