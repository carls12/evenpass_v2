export function PageHead({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return (
    <section className="page-head">
      <div className="hero-glow" aria-hidden="true" />
      <div className="container">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {text && <p className="lead">{text}</p>}
      </div>
    </section>
  );
}
