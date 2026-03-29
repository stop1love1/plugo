import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Sites from "./pages/Sites";
import Setup from "./pages/Setup";
import Knowledge from "./pages/Knowledge";
import Tools from "./pages/Tools";
import Embed from "./pages/Embed";
import ChatLog from "./pages/ChatLog";
import Visitors from "./pages/Visitors";
import Settings from "./pages/Settings";
import Analytics from "./pages/Analytics";
import AuditLog from "./pages/AuditLog";
import Playground from "./pages/Playground";
import CrawledPages from "./pages/CrawledPages";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Sites />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="site/:siteId">
          <Route path="analytics" element={<Analytics />} />
          <Route path="setup" element={<Setup />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="crawled-pages" element={<CrawledPages />} />
          <Route path="tools" element={<Tools />} />
          <Route path="embed" element={<Embed />} />
          <Route path="playground" element={<Playground />} />
          <Route path="chat-log" element={<ChatLog />} />
          <Route path="visitors" element={<Visitors />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
