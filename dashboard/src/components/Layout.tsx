import { Outlet, Link, useParams, useLocation, useNavigate } from "react-router-dom";
import { MessageSquare, Database, Wrench, Code, Settings, LayoutDashboard, MessageCircle, LogOut, User, Brain, BarChart3, Globe, Users, FileText, Keyboard } from "lucide-react";
import { useStore } from "../lib/store";
import { useLocale } from "../lib/useLocale";
import { NotificationBell } from "./NotificationBell";
import { useKeyboardShortcuts } from "../lib/useKeyboardShortcuts";
import { useState } from "react";

const sidebarLinks = [
  { to: "analytics", label: "nav.analytics", icon: BarChart3, num: "1" },
  { to: "setup", label: "nav.setup", icon: LayoutDashboard, num: "2" },
  { to: "knowledge", label: "nav.knowledge", icon: Database, num: "3" },
  { to: "tools", label: "nav.tools", icon: Wrench, num: "4" },
  { to: "embed", label: "nav.embed", icon: Code, num: "5" },
  { to: "chat-log", label: "nav.chatLog", icon: MessageCircle, num: "6" },
  { to: "visitors", label: "nav.visitors", icon: Brain, num: "7" },
  { to: "settings", label: "nav.settings", icon: Settings, num: "8" },
];

const globalLinks = [
  { to: "/users", label: "nav.users", icon: Users },
  { to: "/audit", label: "nav.audit", icon: FileText },
];

export default function Layout() {
  const { siteId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useStore();
  const { locale, setLocale, t } = useLocale();
  const [showShortcuts, setShowShortcuts] = useState(false);

  useKeyboardShortcuts();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Fallback translations for nav items not yet in i18n
  const navT = (key: string) => {
    const val = t(key);
    if (val === key) {
      // Fallback for keys not in i18n
      const fallbacks: Record<string, string> = {
        "nav.setup": "Crawl & Setup",
        "nav.embed": "Embed Code",
        "nav.chatLog": "Chat Log",
        "nav.users": "Users",
        "nav.audit": "Audit Log",
      };
      return fallbacks[key] || key.split(".").pop() || key;
    }
    return val;
  };

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold text-primary-600">
            <MessageSquare className="w-6 h-6" />
            Plugo
          </Link>
        </div>

        {siteId && (
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {sidebarLinks.map(({ to, label, icon: Icon, num }) => {
              const path = `/site/${siteId}/${to}`;
              const isActive = location.pathname === path;
              return (
                <Link
                  key={to}
                  to={path}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive
                      ? "bg-primary-50 text-primary-700 font-medium"
                      : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="flex-1">{navT(label)}</span>
                  <kbd className="text-[10px] text-gray-300 bg-gray-50 px-1 rounded hidden lg:inline">{num}</kbd>
                </Link>
              );
            })}

            <div className="border-t border-gray-100 my-2 pt-2">
              {globalLinks.map(({ to, label, icon: Icon }) => {
                const isActive = location.pathname === to;
                return (
                  <Link
                    key={to}
                    to={to}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                      isActive
                        ? "bg-primary-50 text-primary-700 font-medium"
                        : "text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {navT(label)}
                  </Link>
                );
              })}
            </div>
          </nav>
        )}

        {!siteId && (
          <nav className="flex-1 p-4">
            <p className="text-sm text-gray-400 mb-4">Select a site to get started</p>
            <div className="space-y-1">
              {globalLinks.map(({ to, label, icon: Icon }) => (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    location.pathname === to
                      ? "bg-primary-50 text-primary-700 font-medium"
                      : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {navT(label)}
                </Link>
              ))}
            </div>
          </nav>
        )}

        {/* User menu */}
        <div className="p-4 border-t border-gray-200">
          {user && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <User className="w-4 h-4 text-gray-400 shrink-0" />
                <span className="text-sm text-gray-600 truncate">{user.username}</span>
                <span className="text-xs bg-primary-50 text-primary-600 px-1.5 py-0.5 rounded shrink-0">
                  {user.role}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <NotificationBell />
                <button
                  onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
                  className="text-xs bg-gray-100 hover:bg-gray-200 px-2 py-1 rounded font-medium text-gray-600 shrink-0 flex items-center gap-1"
                  title={t("settings.language")}
                >
                  <Globe className="w-3 h-3" />
                  {locale === "vi" ? "EN" : "VI"}
                </button>
                <button
                  onClick={handleLogout}
                  className="text-gray-400 hover:text-red-500 p-1"
                  title={t("nav.logout")}
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-gray-400">Plugo v1.0</span>
            <button
              onClick={() => setShowShortcuts(!showShortcuts)}
              className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
              title="Keyboard shortcuts"
            >
              <Keyboard className="w-3 h-3" />
            </button>
          </div>
          {showShortcuts && (
            <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-500 space-y-1">
              <div className="flex justify-between"><span>Ctrl+K</span><span>Search</span></div>
              <div className="flex justify-between"><span>1-8</span><span>Navigate pages</span></div>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
