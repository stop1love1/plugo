import { Outlet, Link, useParams, useLocation, useNavigate } from "react-router-dom";
import { MessageSquare, Database, Wrench, Code, Settings, LayoutDashboard, MessageCircle, LogOut, User, Brain, BarChart3, Globe } from "lucide-react";
import { useStore } from "../lib/store";
import { useLocale } from "../lib/useLocale";

const sidebarLinks = [
  { to: "analytics", label: "Analytics", icon: BarChart3 },
  { to: "setup", label: "Crawl & Setup", icon: LayoutDashboard },
  { to: "knowledge", label: "Knowledge Base", icon: Database },
  { to: "tools", label: "API Tools", icon: Wrench },
  { to: "embed", label: "Embed Code", icon: Code },
  { to: "chat-log", label: "Chat Log", icon: MessageCircle },
  { to: "visitors", label: "Visitor Memory", icon: Brain },
  { to: "settings", label: "Settings", icon: Settings },
];

export default function Layout() {
  const { siteId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useStore();
  const { locale, setLocale, t } = useLocale();

  const handleLogout = () => {
    logout();
    navigate("/login");
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
          <nav className="flex-1 p-4 space-y-1">
            {sidebarLinks.map(({ to, label, icon: Icon }) => {
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
                  {label}
                </Link>
              );
            })}
          </nav>
        )}

        {!siteId && (
          <div className="flex-1 p-4 text-sm text-gray-400">
            Select a site to get started
          </div>
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
          )}
          <div className="text-xs text-gray-400 mt-2">Plugo v1.0 &middot; Open Source</div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
