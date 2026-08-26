/**
 * A titled box. Fully implemented.
 *
 * PROPS: title = str, subtitle = str, children = ReactNode
 */
export default function Panel({ title, subtitle, children }) {
  return (
    <section className="panel">
      <header className="panel__head">
        <h2>{title}</h2>
        {subtitle && <span className="muted">{subtitle}</span>}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
