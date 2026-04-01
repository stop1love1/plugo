import { Outlet, Link, useParams, useLocation, useNavigate } from "react-router-dom";
import { Database, Wrench, Code, Settings, LayoutDashboard, MessageCircle, LogOut, User, Brain, BarChart3, Globe, FileText, Menu, X, Play, Link2, Bell, Cpu, SlidersHorizontal } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getSites } from "../lib/api";
import { useStore } from "../lib/store";
import { useLocale } from "../lib/useLocale";
import { useNotifications } from "../lib/useNotifications";
import { useCallback, useEffect, useState } from "react";

const sidebarGroups = [
  {
    heading: null,
    links: [
      { to: "analytics", label: "nav.analytics", icon: BarChart3 },
    ],
  },
  {
    heading: "nav.group.content",
    links: [
      { to: "setup", label: "nav.setup", icon: LayoutDashboard },
      { to: "knowledge", label: "nav.knowledge", icon: Database },
      { to: "crawled-pages", label: "nav.crawledPages", icon: Link2 },
      { to: "tools", label: "nav.tools", icon: Wrench },
    ],
  },
  {
    heading: "nav.group.deploy",
    links: [
      { to: "embed", label: "nav.embed", icon: Code },
      { to: "playground", label: "nav.playground", icon: Play },
    ],
  },
  {
    heading: "nav.group.monitor",
    links: [
      { to: "chat-log", label: "nav.chatLog", icon: MessageCircle },
      { to: "visitors", label: "nav.visitors", icon: Brain },
    ],
  },
  {
    heading: null,
    links: [
      { to: "settings", label: "nav.settings", icon: Settings },
    ],
  },
];

const globalLinks = [
  { to: "/global-settings", label: "nav.globalSettings", icon: SlidersHorizontal },
  { to: "/models", label: "nav.models", icon: Cpu },
  { to: "/audit", label: "nav.audit", icon: FileText },
];

export default function Layout() {
  const { siteId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useStore();
  const { locale, setLocale, t } = useLocale();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { unreadCount } = useNotifications();

  const notificationsPath = siteId ? `/site/${siteId}/notifications` : "/notifications";
  const isNotificationsActive =
    location.pathname === "/notifications" ||
    (siteId != null && location.pathname === `/site/${siteId}/notifications`);

  // Fallback translations for nav items not yet in i18n
  const navT = useCallback(
    (key: string) => {
      const val = t(key);
      if (val === key) {
        const fallbacks: Record<string, string> = {
          "nav.setup": "Crawl & Setup",
          "nav.embed": "Embed Code",
          "nav.chatLog": "Chat Log",
          "nav.users": "Users",
          "nav.globalSettings": "Global Settings",
          "nav.models": "Models",
          "nav.audit": "Audit Log",
          "nav.group.content": "Content",
          "nav.group.deploy": "Deploy",
          "nav.group.monitor": "Monitor",
        };
        return fallbacks[key] || key.split(".").pop() || key;
      }
      return val;
    },
    [t]
  );

  // Update document title based on current route
  useEffect(() => {
    const path = location.pathname;
    const allLinks = sidebarGroups.flatMap((g) => g.links);
    const match = allLinks.find((link) => path.endsWith(`/${link.to}`));
    if (match) {
      document.title = `${navT(match.label)} | Plugo`;
    } else if (path === "/global-settings") {
      document.title = "Global Settings | Plugo";
    } else if (path === "/models") {
      document.title = "Models | Plugo";
    } else if (path === "/audit") {
      document.title = "Audit Log | Plugo";
    } else if (path === "/notifications" || path.endsWith("/notifications")) {
      document.title = `${t("notifications.title")} | Plugo`;
    } else if (path === "/login") {
      document.title = "Login | Plugo";
    } else {
      document.title = "Plugo Dashboard";
    }
  }, [location.pathname, t, navT]);

  const { data: sites = [] } = useQuery({
    queryKey: ["sites"],
    queryFn: getSites,
  });

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Close sidebar on navigation (mobile)
  const handleNavClick = () => {
    if (window.innerWidth < 1024) setSidebarOpen(false);
  };

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Mobile hamburger */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 bg-white border border-gray-200 rounded-lg p-2 shadow-sm"
        aria-label="Toggle menu"
      >
        {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar overlay on mobile */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 bg-black/30 z-30" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-40 w-64 shrink-0 bg-white border-r border-gray-200 flex flex-col transform transition-transform lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="border-b border-gray-200 px-4 py-3 flex items-center h-16">
          <Link to="/" onClick={handleNavClick} className="flex items-center gap-3 text-2xl font-bold text-primary-600">
            <img src={new URL("../assets/images/logo.png", import.meta.url).href} alt="Plugo" className="h-10 object-contain" />
            Plugo
          </Link>
        </div>

        {siteId && (
          <nav className="flex-1 p-4 overflow-y-auto">
            {/* Site switcher */}
            {sites.length > 0 && (
              <div className="mb-4">
                <select
                  value={siteId}
                  onChange={(e) => {
                    navigate(`/site/${e.target.value}/analytics`);
                    handleNavClick();
                  }}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 outline-none focus:ring-2 focus:ring-primary-500 truncate"
                >
                  {sites.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
            )}
            {sidebarGroups.map((group, gi) => (
              <div key={gi} className={group.heading ? "mt-4" : ""}>
                {group.heading && (
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 px-3 pb-1">
                    {navT(group.heading)}
                  </p>
                )}
                <div className="space-y-0.5">
                  {group.links.map(({ to, label, icon: Icon }) => {
                    const path = `/site/${siteId}/${to}`;
                    const isActive = location.pathname === path;
                    return (
                      <Link
                        key={to}
                        to={path}
                        onClick={handleNavClick}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                          isActive
                            ? "bg-primary-50 text-primary-700 font-medium border-l-2 border-primary-600 pl-[10px]"
                            : "text-gray-600 hover:bg-gray-100"
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                        <span className="flex-1">{navT(label)}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="border-t border-gray-200 mt-4 pt-3">
              <div className="space-y-0.5">
                {globalLinks.map(({ to, label, icon: Icon }) => {
                  const isActive = location.pathname === to;
                  return (
                    <Link
                      key={to}
                      to={to}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                        isActive
                          ? "bg-primary-50 text-primary-700 font-medium border-l-2 border-primary-600 pl-[10px]"
                          : "text-gray-600 hover:bg-gray-100"
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                      {navT(label)}
                    </Link>
                  );
                })}
                <Link
                  to={notificationsPath}
                  onClick={handleNavClick}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors w-full ${
                    isNotificationsActive
                      ? "bg-primary-50 text-primary-700 font-medium border-l-2 border-primary-600 pl-[10px]"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <Bell className="w-5 h-5 shrink-0" />
                  <span className="flex-1 text-left">{t("notifications.title")}</span>
                  {unreadCount > 0 && (
                    <span className="bg-red-500 text-white rounded-full text-[10px] px-1.5 py-0.5 min-w-[18px] text-center shrink-0">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </Link>
                <button
                  onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors w-full"
                >
                  <Globe className="w-5 h-5" />
                  <span className="flex-1 text-left">{locale === "vi" ? "Tiếng Việt" : "English"}</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-red-500 hover:bg-red-50 hover:text-red-600 transition-colors w-full"
                >
                  <LogOut className="w-5 h-5" />
                  <span className="flex-1 text-left">{t("nav.logout")}</span>
                </button>
              </div>
            </div>
          </nav>
        )}

        {!siteId && (
          <nav className="flex-1 p-4 overflow-y-auto">
            {/* Site list */}
            {sites.length > 0 && (
              <div className="mb-4">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 px-3 pb-1">Sites</p>
                <div className="space-y-0.5">
                  {sites.map((s) => (
                    <Link
                      key={s.id}
                      to={`/site/${s.id}/analytics`}
                      onClick={handleNavClick}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors"
                    >
                      <Globe className="w-4 h-4 text-gray-400" />
                      <span className="truncate flex-1">{s.name}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {sites.length === 0 && (
              <p className="text-sm text-gray-400 mb-4">Select a site to get started</p>
            )}
            <div className="border-t border-gray-200 pt-3">
              <div className="space-y-0.5">
                {globalLinks.map(({ to, label, icon: Icon }) => (
                  <Link
                    key={to}
                    to={to}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                      location.pathname === to
                        ? "bg-primary-50 text-primary-700 font-medium border-l-2 border-primary-600 pl-[10px]"
                        : "text-gray-600 hover:bg-gray-100"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    {navT(label)}
                  </Link>
                ))}
                <Link
                  to={notificationsPath}
                  onClick={handleNavClick}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors w-full ${
                    isNotificationsActive
                      ? "bg-primary-50 text-primary-700 font-medium border-l-2 border-primary-600 pl-[10px]"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  <Bell className="w-5 h-5 shrink-0" />
                  <span className="flex-1 text-left">{t("notifications.title")}</span>
                  {unreadCount > 0 && (
                    <span className="bg-red-500 text-white rounded-full text-[10px] px-1.5 py-0.5 min-w-[18px] text-center shrink-0">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </Link>
                <button
                  onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors w-full"
                >
                  <Globe className="w-5 h-5" />
                  <span className="flex-1 text-left">{locale === "vi" ? "Tiếng Việt" : "English"}</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-red-500 hover:bg-red-50 hover:text-red-600 transition-colors w-full"
                >
                  <LogOut className="w-5 h-5" />
                  <span className="flex-1 text-left">{t("nav.logout")}</span>
                </button>
              </div>
            </div>
          </nav>
        )}

        {/* User footer */}
        {user && (
          <div className="border-t border-gray-200 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-primary-50 flex items-center justify-center shrink-0">
                <User className="w-3.5 h-3.5 text-primary-600" />
              </div>
              <span className="text-sm text-gray-600 truncate flex-1">{user.username}</span>
              <span className="text-[10px] text-gray-300">v1.0</span>
            </div>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 p-4 pt-16 lg:p-8 lg:pt-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
