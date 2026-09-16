import { useEffect } from "react";
import { LOGOUT_URL, loginUrl, useAuth } from "./auth";

function Notice({ title, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-gray p-6">
      <div className="bg-white rounded-xl border border-brand-line shadow-sm max-w-md w-full p-8 space-y-3 text-center">
        <p className="text-brand-orange font-bold text-sm">Estella Wilson Properties LLC</p>
        <h1 className="text-lg font-bold text-brand-charcoal">{title}</h1>
        {children}
      </div>
    </div>
  );
}

/**
 * Renders the app only for users who may use it.
 *
 * The Static Web Apps edge rules already keep other users away from the app
 * and the API. This covers deep links, which the platform's SPA fallback
 * serves without applying route rules: without it, a signed-out visitor would
 * see an empty shell instead of the sign-in page.
 */
export default function RequireAccess({ children }) {
  const { status, user } = useAuth();

  useEffect(() => {
    if (status === "signed-out") window.location.assign(loginUrl());
  }, [status]);

  if (status === "authorized" || status === "local") return children;

  if (status === "no-access") {
    return (
      <Notice title="You don't have access yet">
        <p className="text-sm text-gray-600">
          You're signed in as <span className="font-semibold">{user}</span>, but this tool is
          invite-only. Ask the owner for an invitation, open its link, and sign in with this
          Microsoft account.
        </p>
        {/* Static Web Apps adds roles to a session only at sign-in, so a session
            started before the invitation was accepted stays role-less. */}
        <p className="text-xs text-gray-500">
          Already opened your invitation? Access starts with a fresh sign-in: sign out, then sign
          in again.
        </p>
        <a href={LOGOUT_URL} className="inline-block text-sm font-semibold text-brand-orange hover:underline">
          Sign out
        </a>
      </Notice>
    );
  }

  if (status === "error") {
    return (
      <Notice title="Couldn't check your sign-in">
        <p className="text-sm text-gray-600">Check your connection and try again.</p>
        <button
          onClick={() => window.location.reload()}
          className="bg-brand-orange text-white font-bold px-6 py-2 rounded-lg hover:bg-brand-dark transition-colors text-sm"
        >
          Try again
        </button>
      </Notice>
    );
  }

  return <Notice title={status === "signed-out" ? "Redirecting to sign-in…" : "Loading…"} />;
}
