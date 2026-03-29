import { Outlet, Link, useParams, useLocation, useNavigate } from "react-router-dom";
import { Database, Wrench, Code, Settings, LayoutDashboard, MessageCircle, LogOut, User, Brain, BarChart3, Globe, FileText, Keyboard, Menu, X, Play, ExternalLink, Link2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getSite } from "../lib/api";
import { useStore } from "../lib/store";
import { useLocale } from "../lib/useLocale";
import { NotificationBell } from "./NotificationBell";
import { useKeyboardShortcuts } from "../lib/useKeyboardShortcuts";
import { useEffect, useState } from "react";

const sidebarGroups = [
  {
    heading: null,
    links: [
      { to: "analytics", label: "nav.analytics", icon: BarChart3, num: "1" },
    ],
  },
  {
    heading: "nav.group.content",
    links: [
      { to: "setup", label: "nav.setup", icon: LayoutDashboard, num: "2" },
      { to: "knowledge", label: "nav.knowledge", icon: Database, num: "3" },
      { to: "crawled-pages", label: "nav.crawledPages", icon: Link2, num: "" },
      { to: "tools", label: "nav.tools", icon: Wrench, num: "4" },
    ],
  },
  {
    heading: "nav.group.deploy",
    links: [
      { to: "embed", label: "nav.embed", icon: Code, num: "5" },
      { to: "playground", label: "nav.playground", icon: Play, num: "6" },
    ],
  },
  {
    heading: "nav.group.monitor",
    links: [
      { to: "chat-log", label: "nav.chatLog", icon: MessageCircle, num: "7" },
      { to: "visitors", label: "nav.visitors", icon: Brain, num: "8" },
    ],
  },
  {
    heading: null,
    links: [
      { to: "settings", label: "nav.settings", icon: Settings, num: "9" },
    ],
  },
];

const globalLinks = [
  { to: "/audit", label: "nav.audit", icon: FileText },
];

export default function Layout() {
  const { siteId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useStore();
  const { locale, setLocale, t } = useLocale();
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useKeyboardShortcuts();

  // Update document title based on current route
  useEffect(() => {
    const path = location.pathname;
    const allLinks = sidebarGroups.flatMap((g) => g.links);
    const match = allLinks.find((link) => path.endsWith(`/${link.to}`));
    if (match) {
      document.title = `${navT(match.label)} | Plugo`;
    } else if (path === "/audit") {
      document.title = "Audit Log | Plugo";
    } else if (path === "/login") {
      document.title = "Login | Plugo";
    } else {
      document.title = "Plugo Dashboard";
    }
  }, [location.pathname, t]);

  const { data: currentSite } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

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
        "nav.group.content": "Content",
        "nav.group.deploy": "Deploy",
        "nav.group.monitor": "Monitor",
      };
      return fallbacks[key] || key.split(".").pop() || key;
    }
    return val;
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
            {sidebarGroups.map((group, gi) => (
              <div key={gi} className={gi > 0 ? "mt-4" : ""}>
                {group.heading && (
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 px-3 pb-1">
                    {navT(group.heading)}
                  </p>
                )}
                <div className="space-y-0.5">
                  {group.links.map(({ to, label, icon: Icon, num }) => {
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
                        <kbd className="text-[10px] text-gray-300 bg-gray-50 px-1 rounded hidden lg:inline">{num}</kbd>
                      </Link>
                    );
                  })}
                  {/* Demo page link in Deploy group */}
                  {group.heading === "nav.group.deploy" && currentSite?.token && (
                    <a
                      href={`${import.meta.env.VITE_BACKEND_URL || __BACKEND_URL__}/demo/${currentSite.token}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={handleNavClick}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-orange-600 hover:bg-orange-50 transition-colors"
                    >
                      <ExternalLink className="w-5 h-5" />
                      <span className="flex-1">{navT("nav.demo")}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        currentSite.is_approved
                          ? "bg-green-100 text-green-700"
                          : "bg-amber-100 text-amber-700"
                      }`}>
                        {currentSite.is_approved ? navT("sites.statusApproved") : navT("sites.statusPending")}
                      </span>
                    </a>
                  )}
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
              </div>
            </div>
          </nav>
        )}

        {!siteId && (
          <nav className="flex-1 p-4">
            <p className="text-sm text-gray-400 mb-4">Select a site to get started</p>
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
            </div>
          </nav>
        )}

        {/* User menu */}
        <div className="p-4 border-t border-gray-200 space-y-3">
          {user && (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 rounded-full bg-primary-50 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-primary-600" />
                </div>
                <span className="text-sm text-gray-700 font-medium truncate">{user.username}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Plugo v1.0</span>
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
                    onClick={() => setShowShortcuts(!showShortcuts)}
                    className="text-gray-400 hover:text-gray-600 p-1"
                    title="Keyboard shortcuts"
                  >
                    <Keyboard className="w-3.5 h-3.5" />
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
            </>
          )}
          {showShortcuts && (
            <div className="p-2 bg-gray-50 rounded text-xs text-gray-500 space-y-1">
              <div className="flex justify-between"><span>Ctrl+K</span><span>Search</span></div>
              <div className="flex justify-between"><span>1-9</span><span>Navigate pages</span></div>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 min-w-0 p-4 pt-16 lg:p-8 lg:pt-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
