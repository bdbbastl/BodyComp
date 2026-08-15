import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import ClientShell from "./components/ClientShell";
import RequireAuth from "./components/RequireAuth";
import ClientRedirect from "./components/ClientRedirect";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import SignupSuccess from "./pages/SignupSuccess";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import Account from "./pages/Account";
import Timeline from "./pages/Timeline";
import ClientCheckins from "./pages/ClientCheckins";
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";
import Datenschutz from "./pages/legal/Datenschutz";
import Impressum from "./pages/legal/Impressum";
import Agb from "./pages/legal/Agb";
import CheckinSubmit from "./pages/CheckinSubmit";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/signup-success" element={<SignupSuccess />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/checkin/:token" element={<CheckinSubmit />} />
      <Route path="/datenschutz" element={<Datenschutz />} />
      <Route path="/impressum" element={<Impressum />} />
      <Route path="/agb" element={<Agb />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<ClientRedirect />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="account" element={<Account />} />
          <Route path="clients/:clientId" element={<ClientShell />}>
            <Route path="timeline" element={<Timeline />} />
            <Route path="checkins" element={<ClientCheckins />} />
            <Route path="unprocessed" element={<Unprocessed />} />
            <Route path="compare" element={<Compare />} />
            <Route path="statistics" element={<Statistics />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
