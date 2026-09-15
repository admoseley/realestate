import { createContext, useContext } from "react";

// ── Sign-in (Azure Static Web Apps) ──────────────────────────────────────────
// Static Web Apps signs users in with Microsoft accounts and enforces access at
// the edge (public/staticwebapp.config.json): only invited users with the
// analyst or admin role can load the app or call /api. Everything in this file
// is for the interface only. It shows who's signed in, sends signed-out users
// to sign-in when they open a deep link (the platform's SPA fallback serves
// those without applying route rules), and hides admin-only actions from
// analysts. It is not a security boundary.

export const APP_ROLES = ["analyst", "admin"];

export const loginUrl = (returnTo = window.location.pathname + window.location.search) =>
  `/.auth/login/aad?post_login_redirect_uri=${encodeURIComponent(returnTo)}`;

export const LOGOUT_URL = "/.auth/logout?post_logout_redirect_uri=/";

// Outside Static Web Apps (the Vite dev server, or the old Netlify site until
// the cutover) there is no /.auth endpoint, and the request falls through to
// index.html. The interface then runs without sign-in, as it always has there.
const LOCAL = { status: "local", user: "Local development", roles: [...APP_ROLES] };

/** Ask Static Web Apps who is signed in. */
export async function loadAuth() {
  try {
    const response = await fetch("/.auth/me", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const isJson = (response.headers.get("content-type") || "").includes("application/json");
    if (!response.ok || !isJson) return LOCAL;

    const { clientPrincipal } = await response.json();
    if (!clientPrincipal) return { status: "signed-out", user: null, roles: [] };

    const roles = clientPrincipal.userRoles || [];
    return {
      status: roles.some(role => APP_ROLES.includes(role)) ? "authorized" : "no-access",
      user: clientPrincipal.userDetails,
      roles,
    };
  } catch {
    return { status: "error", user: null, roles: [] };
  }
}

export const AuthContext = createContext({ status: "loading", user: null, roles: [] });

/** The current sign-in state: status, user, roles, and whether they're an admin. */
export function useAuth() {
  const auth = useContext(AuthContext);
  return { ...auth, isAdmin: auth.roles.includes("admin") };
}
