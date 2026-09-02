/**
 * The one unauthenticated screen, and the only place in this product that is
 * allowed to be loud.
 *
 * Everything behind the sign-in is an instrument: quiet, dense, hueless chrome.
 * That discipline is right for a room where colour has to mean something, but it
 * gives the product nowhere to say what it IS. So the whole display budget is
 * spent here, once.
 *
 * The motif is the cyclone isobar -- the concentric pressure contours around an
 * eye that this district's forecasts are actually read from. It is the subject's
 * own instrument rather than a decorative gradient, and it is drawn in SVG so it
 * costs nothing to ship and scales to any screen.
 *
 * Nothing here guesses at district state -- there is no session yet to read it
 * with, and inventing a number on a sign-in screen would be a lie an operator
 * could act on.
 */
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks";

/**
 * The isobar field.
 *
 * Deliberately irregular: real pressure contours are squashed ovals at slightly
 * different angles, and a stack of true circles would just read as a target.
 * Alternate rings counter-rotate, which is what stops the whole thing looking
 * like a spinning logo.
 *
 * GEOMETRY RULE: every ring must fit inside the viewBox. An <svg> clips at its
 * own bounds, so a ring wider than the box does not fade out at the edge -- it
 * gets sliced into a hard arc, and a few of those crossing each other read as a
 * tangle rather than as weather. The widest ring here is 460 in a 1000 box.
 */
function StormField() {
  /* NESTING RULE: contours never cross. Giving each ring its own rotation broke
     that -- a ring turned 50 degrees pokes straight out through the slightly
     larger one turned 44, and eight of those read as a tangle of arcs rather
     than as weather. So every ring shares one angle and one axis ratio, and the
     eccentricity comes from drifting the CENTRE instead. Each step out moves the
     centre by 9 units and grows the radius by at least 48, so containment is
     guaranteed. This is also what a real pressure chart looks like: contours
     nest, and the whole stack leans. */
  const ANGLE = 24;
  const RATIO = 0.76;
  const radii = [52, 104, 164, 232, 308, 392, 470];

  return (
    <svg
      className="login__storm"
      viewBox="0 0 1000 1000"
      aria-hidden="true"
      focusable="false"
    >
      <g transform={`rotate(${ANGLE} 500 500)`}>
        {radii.map((rx, i) => (
          <ellipse
            key={rx}
            className={`isobar${i % 3 === 1 ? " isobar--dashed" : ""}`}
            cx={500 + i * 9}
            cy={500 - i * 5}
            rx={rx}
            ry={rx * RATIO}
            /* The gradient tightens towards the centre, the way it does on a
               chart: the outer contours are the faintest. */
            style={{ opacity: 1 - i * 0.11 }}
          />
        ))}
        {/* The eye. A ring, not a filled disc -- a disc behind the wordmark read
            as a smudge under the type rather than as the centre of a storm. */}
        <ellipse className="isobar eye" cx="500" cy="500" rx="20" ry={20 * RATIO} />
      </g>
    </svg>
  );
}

export default function LoginPage() {
  const { signIn, pending, error, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    try {
      await signIn(username, password);
      navigate("/", { replace: true });
    } catch {
      /* `error` from the hook already carries the message */
    }
  }

  return (
    <div className="login">
      <section className="login__brand">
        <StormField />

        <span className="login__eyebrow">Puri district · Odisha</span>
        <h1 className="login__mark">DISHA</h1>
        <p className="login__blurb">
          Reports in, units out — one picture of the district, shared by everyone
          working it.
        </p>

        {/* What the system does, not numbers it cannot know before sign-in. */}
        <div className="login__facts">
          <div className="login__fact">
            <b>Live</b>
            <span className="label">district map</span>
          </div>
          <div className="login__fact">
            <b>SMS</b>
            <span className="label">when the network drops</span>
          </div>
          <div className="login__fact">
            <b>Audited</b>
            <span className="label">every dispatch explained</span>
          </div>
        </div>
      </section>

      <div className="login__panel">
        <form className="login-card" onSubmit={onSubmit}>
          <h2 className="login-card__title">Sign in</h2>
          <p className="login-card__hint">Use the credentials issued for your post.</p>

          <div className="field">
            <label className="label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p className="error" role="alert">
              {error.detail}
            </p>
          )}

          <button type="submit" className="btn--commit" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
