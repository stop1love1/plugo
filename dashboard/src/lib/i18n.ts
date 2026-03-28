export type Locale = "vi" | "en";

const translations: Record<Locale, Record<string, string>> = {
  vi: {
    // Nav
    "nav.sites": "Trang web",
    "nav.knowledge": "Kiến thức",
    "nav.tools": "Công cụ API",
    "nav.settings": "Cài đặt",
    "nav.analytics": "Phân tích",
    "nav.visitors": "Khách truy cập",
    "nav.logout": "Đăng xuất",
    // Common
    "common.save": "Lưu",
    "common.cancel": "Hủy",
    "common.delete": "Xóa",
    "common.edit": "Sửa",
    "common.add": "Thêm",
    "common.search": "Tìm kiếm...",
    "common.loading": "Đang tải...",
    "common.confirm": "Xác nhận",
    "common.previous": "Trước",
    "common.next": "Tiếp",
    "common.page": "Trang",
    "common.selected": "đã chọn",
    "common.deleteSelected": "Xóa đã chọn",
    "common.clearSelection": "Bỏ chọn",
    "common.noResults": "Không có kết quả.",
    // Sites
    "sites.title": "Trang web",
    "sites.subtitle": "Quản lý các trang web của bạn",
    "sites.addSite": "Thêm trang web",
    "sites.noSites": "Chưa có trang web nào.",
    // Knowledge
    "knowledge.title": "Kiến thức",
    "knowledge.addManual": "Thêm thủ công",
    "knowledge.uploadFile": "Tải file lên",
    "knowledge.searchKnowledge": "Tìm kiếm kiến thức...",
    "knowledge.noData": "Chưa có dữ liệu. Crawl trang web hoặc thêm nội dung thủ công.",
    "knowledge.chunks": "chunks",
    "knowledge.confirmDelete": "Bạn có chắc muốn xóa?",
    // Tools
    "tools.title": "Công cụ API",
    "tools.subtitle": "Cho phép bot gọi API của trang web",
    "tools.addTool": "Thêm công cụ",
    "tools.importOpenAPI": "Nhập từ OpenAPI",
    "tools.noTools": "Chưa có công cụ. Thêm API tool để bot thực hiện hành động.",
    "tools.toolName": "Tên công cụ",
    "tools.method": "Phương thức",
    "tools.description": "Mô tả (giúp bot quyết định khi nào gọi tool)",
    "tools.url": "URL",
    "tools.authType": "Loại xác thực",
    "tools.authValue": "Giá trị xác thực",
    "tools.paramsSchema": "Schema tham số (JSON)",
    // Settings
    "settings.title": "Cài đặt",
    "settings.widget": "Widget",
    "settings.llm": "Mô hình AI",
    "settings.crawl": "Crawl",
    "settings.language": "Ngôn ngữ",
    // Login
    "login.title": "Đăng nhập",
    "login.username": "Tên đăng nhập",
    "login.password": "Mật khẩu",
    "login.submit": "Đăng nhập",
    "login.error": "Sai tên đăng nhập hoặc mật khẩu",
  },
  en: {
    // Nav
    "nav.sites": "Sites",
    "nav.knowledge": "Knowledge",
    "nav.tools": "API Tools",
    "nav.settings": "Settings",
    "nav.analytics": "Analytics",
    "nav.visitors": "Visitors",
    "nav.logout": "Logout",
    // Common
    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.delete": "Delete",
    "common.edit": "Edit",
    "common.add": "Add",
    "common.search": "Search...",
    "common.loading": "Loading...",
    "common.confirm": "Confirm",
    "common.previous": "Previous",
    "common.next": "Next",
    "common.page": "Page",
    "common.selected": "selected",
    "common.deleteSelected": "Delete Selected",
    "common.clearSelection": "Clear selection",
    "common.noResults": "No results found.",
    // Sites
    "sites.title": "Sites",
    "sites.subtitle": "Manage your websites",
    "sites.addSite": "Add Site",
    "sites.noSites": "No sites yet.",
    // Knowledge
    "knowledge.title": "Knowledge Base",
    "knowledge.addManual": "Add Manually",
    "knowledge.uploadFile": "Upload File",
    "knowledge.searchKnowledge": "Search knowledge...",
    "knowledge.noData": "No data yet. Crawl your website or add content manually.",
    "knowledge.chunks": "chunks",
    "knowledge.confirmDelete": "Are you sure you want to delete?",
    // Tools
    "tools.title": "API Tools",
    "tools.subtitle": "Let the bot call your website's APIs",
    "tools.addTool": "Add Tool",
    "tools.importOpenAPI": "Import from OpenAPI",
    "tools.noTools": "No tools yet. Add an API tool to enable the bot to perform actions.",
    "tools.toolName": "Tool Name",
    "tools.method": "Method",
    "tools.description": "Description (helps the bot decide when to call this tool)",
    "tools.url": "URL",
    "tools.authType": "Auth Type",
    "tools.authValue": "Auth Value",
    "tools.paramsSchema": "Params Schema (JSON)",
    // Settings
    "settings.title": "Settings",
    "settings.widget": "Widget",
    "settings.llm": "AI Model",
    "settings.crawl": "Crawl",
    "settings.language": "Language",
    // Login
    "login.title": "Sign In",
    "login.username": "Username",
    "login.password": "Password",
    "login.submit": "Sign In",
    "login.error": "Invalid username or password",
  },
};

const LOCALE_KEY = "plugo_locale";

function getSavedLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved === "vi" || saved === "en") return saved;
  } catch {}
  // Default to Vietnamese
  return "vi";
}

let currentLocale: Locale = getSavedLocale();
const listeners: Set<() => void> = new Set();

export function getLocale(): Locale {
  return currentLocale;
}

export function setLocale(locale: Locale) {
  currentLocale = locale;
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {}
  listeners.forEach((fn) => fn());
}

export function t(key: string): string {
  return translations[currentLocale][key] || key;
}

export function onLocaleChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
