import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
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
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";
import Datenschutz from "./pages/legal/Datenschutz";
import Impressum from "./pages/legal/Impressum";
import Agb from "./pages/legal/Agb";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/signup-success" element={<SignupSuccess />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/datenschutz" element={<Datenschutz />} />
      <Route path="/impressum" element={<Impressum />} />
      <Route path="/agb" element={<Agb />} />
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
