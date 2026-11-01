import { SITE } from '../config/site';
import { Icon, type IconName } from '../components/Icon';
import { PageHead } from './PageHead';

export function Contact() {
  const { email, phone, address } = SITE.contact;
  const items: { icon: IconName; label: string; value: string; href?: string }[] = [
    { icon: 'mail', label: 'Email', value: email, href: email ? `mailto:${email}` : undefined },
    { icon: 'phone', label: 'Phone', value: phone, href: phone ? `tel:${phone.replace(/[^+\d]/g, '')}` : undefined },
    { icon: 'pin', label: 'Address', value: address },
  ];
  return (
    <>
      <PageHead eyebrow="Contact" title="Get in touch" text="Questions about an application, an event or access? We are happy to help." />
      <section className="section section-tight">
        <div className="container contact-grid">
          {items.map((item) => (
            <div className="contact-card reveal" key={item.label}>
              <span className="pillar-icon"><Icon name={item.icon} /></span>
              <h3>{item.label}</h3>
              {item.value ? (
                item.href ? <a href={item.href}>{item.value}</a> : <p>{item.value}</p>
              ) : (
                <p className="muted">To be announced</p>
              )}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
