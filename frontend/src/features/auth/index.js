/**
 * Public surface of the auth feature. Nothing outside this folder may import
 * from its internals -- import from "@/features/auth" instead.
 *
 * The one deliberate exception is shared/api/client.js, which imports ./store
 * directly: the interceptor needs the token before React has rendered anything,
 * so it cannot go through a hook.
 */
export { useAuthStore } from "./store";
export { useAuth, useSyncUser } from "./hooks";
export { login, refreshTokens, fetchMe } from "./api";
export { default as LoginPage } from "./pages/LoginPage";
