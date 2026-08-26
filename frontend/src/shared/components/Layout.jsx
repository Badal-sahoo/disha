/**
 * The chrome around every authenticated screen. Fully implemented.
 */
import { useAuth } from "@/features/auth/hooks";
import { useLiveStore } from "@/shared/store/liveStore";

export default function Layout({ children }) {
  const { user, signOut } = useAuth();
  const connected = useLiveStore((s) => s.connected);
  const lastSyncAt = useLiveStore((s) => s.lastSyncAt);

  return (
    <div className="layout">
      <header className="layout__bar">
        <div className="layout__brand">
          <strong>PS-05</strong>
          <span className="muted">Disaster response operations</span>
        </div>

        <div className="layout__right">
          <span className={connected ? "pill is-live" : "pill"}>
            {connected ? "socket live" : "reconnecting"}
          </span>
          {lastSyncAt && (
            <span className="muted">synced {new Date(lastSyncAt).toLocaleTimeString()}</span>
          )}
          <span className="muted">
            {user?.username} - {user?.role}
          </span>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="layout__body">{children}</div>
    </div>
  );
}
