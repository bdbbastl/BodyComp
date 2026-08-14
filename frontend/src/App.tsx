import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import ClientRedirect from "./components/ClientRedirect";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Account from "./pages/Account";
import Timeline from "./pages/Timeline";
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="account" element={<Account />} />
          <Route path="clients/:clientId/timeline" element={<Timeline />} />
          <Route path="clients/:clientId/unprocessed" element={<Unprocessed />} />
          <Route path="clients/:clientId/compare" element={<Compare />} />
          <Route path="clients/:clientId/statistics" element={<Statistics />} />
          <Route path="clients/:clientId/settings" element={<Settings />} />
        </Route>
      </Route>
    </Routes>
  );
}
