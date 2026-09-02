/**
 * Dark / light theme for the dashboard chrome.
 *
 * Everything is already painted from CSS variables, so switching the theme is
 * just setting data-theme on <html> and letting styles.css redefine them.
 * The map is not affected -- that stays the standard basemap either way.
 */
import { useEffect, useState } from "react";

const STORAGE_KEY = "ps05.theme";

/** The saved choice, or the operating system's preference on a first visit. */
function initialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* private window -- fall through to the system preference */
  }
  const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)").matches;
  return prefersLight ? "light" : "dark";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* the choice just does not survive a reload */
    }
  }, [theme]);

  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(next)}
      title={`Switch to ${next} theme`}
      aria-label={`Switch to ${next} theme`}
    >
      {theme === "dark" ? "☀ Light" : "☾ Dark"}
    </button>
  );
}
