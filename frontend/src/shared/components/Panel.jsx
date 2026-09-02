/**
 * A titled box.
 *
 * Every panel is wrapped in an ErrorBoundary, so one feature throwing shows a
 * message in its own box instead of blanking the whole dashboard.
 *
 * PROPS: title = str, subtitle = str, children = ReactNode
 */
import ErrorBoundary from "./ErrorBoundary";

export default function Panel({ title, subtitle, children }) {
  return (
    <section className="panel">
      <header className="panel__head">
        <h2>{title}</h2>
        {subtitle && <span className="muted">{subtitle}</span>}
      </header>
      <div className="panel__body">
        <ErrorBoundary label={`${title} failed`}>{children}</ErrorBoundary>
      </div>
    </section>
  );
}
