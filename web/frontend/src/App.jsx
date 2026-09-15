import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import SheriffSale from "./pages/SheriffSale";
import SpotCheck from "./pages/SpotCheck";
import History from "./pages/History";
import AuthProvider from "./auth/AuthProvider";
import RequireAccess from "./auth/RequireAccess";

export default function App() {
  // Sign-in state loads once for the whole app. RequireAccess shows sign-in and
  // access messages in place of the app to anyone who can't use it.
  return (
    <AuthProvider>
      <RequireAccess>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="sheriff-sale" element={<SheriffSale />} />
              <Route path="spot-check" element={<SpotCheck />} />
              <Route path="history" element={<History />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </RequireAccess>
    </AuthProvider>
  );
}
