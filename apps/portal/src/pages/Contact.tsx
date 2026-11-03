import { SITE } from '../config/site';
import { Icon, type IconName } from '../components/Icon';
import { t } from '../i18n';
import { PageHead } from './PageHead';

export function Contact() {
  const { email, phone, address } = SITE.contact;
  const items: { icon: IconName; label: string; value: string; href?: string }[] = [
    { icon: 'mail', label: t('contact.email'), value: email, href: email ? `mailto:${email}` : undefined },
    { icon: 'phone', label: t('contact.phone'), value: phone, href: phone ? `tel:${phone.replace(/[^+\d]/g, '')}` : undefined },
    { icon: 'pin', label: t('contact.address'), value: address },
  ];
  return (
    <>
      <PageHead eyebrow={t('contact.eyebrow')} title={t('contact.title')} text={t('contact.text')} />
      <section className="section section-tight">
        <div className="container contact-grid">
          {items.map((item) => (
            <div className="contact-card reveal" key={item.icon}>
              <span className="pillar-icon"><Icon name={item.icon} /></span>
              <h3>{item.label}</h3>
              {item.value ? (
                item.href ? <a href={item.href}>{item.value}</a> : <p>{item.value}</p>
              ) : (
                <p className="muted">{t('contact.tba')}</p>
              )}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
