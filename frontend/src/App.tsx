import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Timeline from "./pages/Timeline";
import Unprocessed from "./pages/Unprocessed";
import Compare from "./pages/Compare";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Timeline />} />
        <Route path="unprocessed" element={<Unprocessed />} />
        <Route path="compare" element={<Compare />} />
        <Route path="statistics" element={<Statistics />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
