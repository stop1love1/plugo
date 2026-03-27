import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Sites from "./pages/Sites";
import Setup from "./pages/Setup";
import Knowledge from "./pages/Knowledge";
import Tools from "./pages/Tools";
import Embed from "./pages/Embed";
import ChatLog from "./pages/ChatLog";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Sites />} />
        <Route path="site/:siteId">
          <Route path="setup" element={<Setup />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="tools" element={<Tools />} />
          <Route path="embed" element={<Embed />} />
          <Route path="chat-log" element={<ChatLog />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
