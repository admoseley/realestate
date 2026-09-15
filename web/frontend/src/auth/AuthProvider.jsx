import { useEffect, useState } from "react";
import { AuthContext, loadAuth } from "./auth";

/** Loads the signed-in user once, for the whole app. */
export default function AuthProvider({ children }) {
  const [auth, setAuth] = useState({ status: "loading", user: null, roles: [] });

  useEffect(() => {
    let active = true;
    loadAuth().then(result => { if (active) setAuth(result); });
    return () => { active = false; };
  }, []);

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}
