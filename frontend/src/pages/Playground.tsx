import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite, type Site } from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { Play, RotateCcw, Monitor, Smartphone, Tablet, Sun, Moon, ExternalLink } from "lucide-react";

type Device = "desktop" | "tablet" | "mobile";

const deviceStyles: Record<Device, { width: string; height: string; label: string }> = {
  desktop: { width: "100%", height: "100%", label: "Desktop" },
  tablet: { width: "768px", height: "100%", label: "Tablet" },
  mobile: { width: "375px", height: "100%", label: "Mobile" },
};

export default function Playground() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [darkMode, setDarkMode] = useState(false);
  const [demoPage, setDemoPage] = useState("store");
  const [key, setKey] = useState(0);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const backendUrl = import.meta.env.VITE_BACKEND_URL || __BACKEND_URL__;
  const demoPages: Record<string, { title: string; content: string }> = {
    store: {
      title: "Store",
      content: getDemoStorePage(site, darkMode, backendUrl),
    },
    account: {
      title: "Account",
      content: getDemoAccountPage(site, darkMode, backendUrl),
    },
    support: {
      title: "Support",
      content: getDemoSupportPage(site, darkMode, backendUrl),
    },
    blank: {
      title: t("playground.pageBlank"),
      content: getDemoBlankPage(site, darkMode),
    },
  };

  useEffect(() => {
    if (iframeRef.current && site) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(demoPages[demoPage].content);
        doc.close();
      }
    }
  }, [site, demoPage, darkMode, key]);

  const handleReload = () => setKey((k) => k + 1);

  const handleOpenExternal = () => {
    if (!site) return;
    const blob = new Blob([demoPages[demoPage].content], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  };

  if (!site) {
    return <div className="flex items-center justify-center h-64 text-gray-400">{t("common.loading")}</div>;
  }

  const deviceStyle = deviceStyles[device];

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("playground.title")}</h1>
          <p className="text-gray-500 text-sm">{t("playground.subtitle")}</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="bg-white border border-gray-200 rounded-t-xl px-4 py-2 flex items-center justify-between">
        {/* Left: Page selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-medium mr-1">{t("playground.page")}:</span>
          {Object.entries(demoPages).map(([id, page]) => (
            <button
              key={id}
              onClick={() => setDemoPage(id)}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                demoPage === id
                  ? "bg-primary-100 text-primary-700 font-medium"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              {page.title}
            </button>
          ))}
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-1">
          {/* Device selector */}
          {[
            { id: "desktop" as Device, icon: Monitor },
            { id: "tablet" as Device, icon: Tablet },
            { id: "mobile" as Device, icon: Smartphone },
          ].map(({ id, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setDevice(id)}
              className={`p-1.5 rounded transition-colors ${
                device === id ? "bg-gray-200 text-gray-800" : "text-gray-400 hover:text-gray-600"
              }`}
              title={deviceStyles[id].label}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}

          <div className="w-px h-5 bg-gray-200 mx-1" />

          {/* Dark mode */}
          <button
            onClick={() => setDarkMode(!darkMode)}
            className={`p-1.5 rounded transition-colors ${
              darkMode ? "bg-gray-700 text-yellow-400" : "text-gray-400 hover:text-gray-600"
            }`}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Reload */}
          <button
            onClick={handleReload}
            className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors"
            title={t("playground.reload")}
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {/* Open external */}
          <button
            onClick={handleOpenExternal}
            className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors"
            title={t("playground.openExternal")}
          >
            <ExternalLink className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Preview area */}
      <div className="flex-1 bg-gray-100 border border-t-0 border-gray-200 rounded-b-xl flex items-start justify-center overflow-hidden p-4">
        <div
          className="bg-white shadow-lg rounded-lg overflow-hidden transition-all duration-300 h-full"
          style={{
            width: deviceStyle.width,
            maxWidth: "100%",
          }}
        >
          <iframe
            ref={iframeRef}
            key={key}
            title="Widget Playground"
            className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          />
        </div>
      </div>

      {/* Info bar */}
      <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
        <span>
          Token: <code className="bg-gray-100 px-1 rounded">{site.token?.slice(0, 12)}...</code>
        </span>
        <span className="flex items-center gap-1">
          <Play className="w-3 h-3" />
          {t("playground.liveChat")}
        </span>
      </div>
    </div>
  );
}

// --- HTML escaping for safe injection into template strings ---

const escapeHtml = (str: string) =>
  str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// --- Demo page generators ---

function getWidgetScript(site: Site, darkMode: boolean, backendUrl?: string): string {
  const bUrl = backendUrl || import.meta.env.VITE_BACKEND_URL || __BACKEND_URL__;
  const wsBackendUrl = bUrl.replace(/^http/, "ws");
  return `
<script>
  window.PlugoConfig = {
    token: ${JSON.stringify(site.token || "")},
    serverUrl: ${JSON.stringify(wsBackendUrl)},
    primaryColor: ${JSON.stringify(site.primary_color || "#6366f1")},
    greeting: ${JSON.stringify(site.greeting || "Hello! How can I help you?")},
    position: ${JSON.stringify(site.position || "bottom-right")},
    darkMode: ${darkMode},
    widgetTitle: ${JSON.stringify(site.widget_title || "")},
    showBranding: ${site.show_branding !== false}
  };
</script>
<script src="${escapeHtml(bUrl)}/static/widget.js" async></script>`;
}

function baseStyles(dark: boolean, accent: string): string {
  const bg = dark ? "#0f172a" : "#f8fafc";
  const text = dark ? "#e2e8f0" : "#1e293b";
  const muted = dark ? "#94a3b8" : "#64748b";
  const card = dark ? "#1e293b" : "#ffffff";
  const border = dark ? "#334155" : "#e2e8f0";
  return `
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: ${bg}; color: ${text}; line-height: 1.6; }
    .container { max-width: 1000px; margin: 0 auto; padding: 0 24px; }
    .muted { color: ${muted}; }
    .card { background: ${card}; border: 1px solid ${border}; border-radius: 12px; padding: 20px; }
    a { color: ${accent}; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .btn { display: inline-block; background: ${accent}; color: #fff; padding: 10px 24px; border-radius: 8px; font-weight: 600; font-size: 0.875rem; border: none; cursor: pointer; }
    .btn:hover { opacity: 0.9; text-decoration: none; }
    .btn-outline { background: none; border: 1.5px solid ${accent}; color: ${accent}; }
    .btn-outline:hover { background: ${accent}; color: #fff; }
    .nav { padding: 12px 0; border-bottom: 1px solid ${border}; display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
    .nav-brand { font-weight: 700; font-size: 1.2rem; color: ${accent}; display: flex; align-items: center; gap: 8px; }
    .nav-links { display: flex; gap: 20px; font-size: 0.85rem; align-items: center; }
    .nav-links a { color: ${muted}; }
    .badge { display: inline-block; background: ${accent}20; color: ${accent}; font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 99px; }
    .grid { display: grid; gap: 16px; }
    .grid-2 { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
    .grid-3 { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
    .toast { position: fixed; top: 20px; right: 20px; background: #22c55e; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 0.85rem; font-weight: 500; z-index: 9999; animation: fadeInOut 2.5s ease; }
    @keyframes fadeInOut { 0% { opacity: 0; transform: translateY(-10px); } 10% { opacity: 1; transform: translateY(0); } 80% { opacity: 1; } 100% { opacity: 0; } }
    .footer { padding: 24px 0; text-align: center; font-size: 0.75rem; color: ${muted}; border-top: 1px solid ${border}; margin-top: 40px; }
    .section-title { font-size: 1.25rem; font-weight: 700; margin-bottom: 16px; }
    .price { font-weight: 800; color: ${accent}; }
    .stock { font-size: 0.75rem; color: ${muted}; }
    .rating { font-size: 0.8rem; color: #f59e0b; }
    .product-img { width: 100%; height: 140px; background: ${dark ? "#334155" : "#f1f5f9"}; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 2rem; margin-bottom: 12px; }
    .cart-badge { background: #ef4444; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 99px; margin-left: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid ${border}; }
    th { font-weight: 600; font-size: 0.75rem; text-transform: uppercase; color: ${muted}; }
    input, textarea, select { font-family: inherit; font-size: 0.875rem; padding: 8px 12px; border: 1px solid ${border}; border-radius: 8px; background: ${card}; color: ${text}; outline: none; width: 100%; }
    input:focus, textarea:focus { border-color: ${accent}; }
    .form-group { margin-bottom: 12px; }
    .form-group label { display: block; font-size: 0.8rem; font-weight: 500; margin-bottom: 4px; color: ${muted}; }
    .status-confirmed { color: #22c55e; font-weight: 600; }
    .status-open { color: #3b82f6; font-weight: 600; }
  `;
}

const PRODUCT_EMOJIS: Record<string, string> = {
  headphones: "\u{1F3A7}", watch: "\u{231A}", coffee: "\u2615",
  chair: "\u{1FA91}", shoes: "\u{1F45F}", keyboard: "\u2328",
  yogamat: "\u{1F9D8}", speaker: "\u{1F50A}",
};

function getDemoStorePage(site: Site | undefined, dark: boolean, backendUrl: string): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - Store</title>
<meta name="description" content="Demo e-commerce store for ${safeName}. Browse products, add to cart, and place orders. The AI assistant can help you shop!">
<style>${baseStyles(dark, accent)}</style></head><body>
<div class="container">
  <nav class="nav">
    <div class="nav-brand">\u{1F6CD}\uFE0F ${safeName}</div>
    <div class="nav-links">
      <a href="#" onclick="filterProducts('')">All</a>
      <a href="#" onclick="filterProducts('electronics')">Electronics</a>
      <a href="#" onclick="filterProducts('sports')">Sports</a>
      <a href="#" onclick="filterProducts('food')">Food</a>
      <a id="cart-link" href="#" onclick="viewCart()">\u{1F6D2} Cart <span id="cart-count" class="cart-badge" style="display:none">0</span></a>
      <a id="auth-link" href="#" onclick="showLogin()">Login</a>
    </div>
  </nav>
  <div style="margin-bottom:16px;display:flex;gap:8px;align-items:center">
    <input id="search" type="text" placeholder="Search products..." style="max-width:300px" onkeyup="if(event.key==='Enter')searchProducts()">
    <button class="btn" onclick="searchProducts()">Search</button>
  </div>
  <h2 class="section-title">Products</h2>
  <div id="products" class="grid grid-2"></div>
  <div id="cart-panel" style="display:none"></div>
  <div id="login-panel" style="display:none"></div>
  <footer class="footer">${safeName} Demo Store \u2014 Powered by Plugo. Try asking the AI to help you shop!</footer>
</div>
<div id="toast-container"></div>
${getWidgetScript(site, dark, backendUrl)}
<script>
const API = ${JSON.stringify(backendUrl + "/api/demo")};
let authToken = null;
let userName = null;
const emojis = ${JSON.stringify(PRODUCT_EMOJIS)};
function toast(msg) {
  const el = document.createElement('div'); el.className = 'toast'; el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 2600);
}
async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  const r = await fetch(API + path, { ...opts, headers });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
  return r.json();
}
function renderProducts(products) {
  const el = document.getElementById('products');
  el.innerHTML = products.map(p => '<div class="card">' +
    '<div class="product-img">' + (emojis[p.image] || '\u{1F4E6}') + '</div>' +
    '<h3 style="font-size:0.95rem;margin-bottom:4px">' + p.name + '</h3>' +
    '<div class="rating">' + '\u2B50'.repeat(Math.round(p.rating)) + ' ' + p.rating + '</div>' +
    '<p style="font-size:0.8rem;margin:6px 0" class="muted">' + p.description + '</p>' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">' +
    '<span class="price">$' + p.price.toFixed(2) + '</span>' +
    '<button class="btn" onclick="addToCart(' + p.id + ')" style="padding:6px 16px;font-size:0.8rem">Add to Cart</button>' +
    '</div><div class="stock">' + p.stock + ' in stock</div></div>').join('');
}
async function loadProducts(cat, search) {
  let q = '/products?';
  if (cat) q += 'category=' + cat + '&';
  if (search) q += 'search=' + encodeURIComponent(search);
  const data = await apiFetch(q);
  renderProducts(data.products);
}
function filterProducts(cat) { loadProducts(cat, ''); }
function searchProducts() { loadProducts('', document.getElementById('search').value); }
async function addToCart(pid) {
  if (!authToken) { toast('Please log in first!'); showLogin(); return; }
  try {
    const data = await apiFetch('/cart/add', { method: 'POST', body: JSON.stringify({ product_id: pid, quantity: 1 }) });
    document.getElementById('cart-count').textContent = data.item_count;
    document.getElementById('cart-count').style.display = data.item_count > 0 ? 'inline' : 'none';
    toast('Added to cart!');
  } catch (e) { toast(e.message); }
}
async function viewCart() {
  if (!authToken) { toast('Please log in first!'); showLogin(); return; }
  try {
    const data = await apiFetch('/cart');
    const panel = document.getElementById('cart-panel');
    if (data.items.length === 0) {
      panel.innerHTML = '<div class="card" style="margin-top:20px"><h3>Your Cart</h3><p class="muted" style="margin-top:8px">Cart is empty</p></div>';
    } else {
      panel.innerHTML = '<div class="card" style="margin-top:20px"><h3>Your Cart</h3><table><tr><th>Item</th><th>Qty</th><th>Price</th><th></th></tr>' +
        data.items.map(i => '<tr><td>' + i.name + '</td><td>' + i.quantity + '</td><td>$' + (i.price * i.quantity).toFixed(2) + '</td><td><a href="#" onclick="removeFromCart(' + i.product_id + ')">Remove</a></td></tr>').join('') +
        '</table><div style="text-align:right;margin-top:12px;font-size:1.1rem"><strong>Total: $' + data.total.toFixed(2) + '</strong></div>' +
        '<div style="text-align:right;margin-top:8px"><button class="btn" onclick="placeOrder()">Place Order</button></div></div>';
    }
    panel.style.display = 'block';
  } catch (e) { toast(e.message); }
}
async function removeFromCart(pid) {
  try {
    const data = await apiFetch('/cart/remove', { method: 'POST', body: JSON.stringify({ product_id: pid }) });
    document.getElementById('cart-count').textContent = data.item_count;
    document.getElementById('cart-count').style.display = data.item_count > 0 ? 'inline' : 'none';
    viewCart();
  } catch (e) { toast(e.message); }
}
async function placeOrder() {
  try {
    const data = await apiFetch('/orders/create', { method: 'POST' });
    document.getElementById('cart-count').textContent = '0';
    document.getElementById('cart-count').style.display = 'none';
    document.getElementById('cart-panel').innerHTML = '<div class="card" style="margin-top:20px"><h3>\u2705 Order Placed!</h3><p style="margin-top:8px">Order <strong>' + data.order.id + '</strong> confirmed. Total: $' + data.order.total.toFixed(2) + '</p><p class="muted">Estimated delivery: ' + data.order.estimated_delivery + '</p></div>';
    toast('Order placed!');
  } catch (e) { toast(e.message); }
}
function showLogin() {
  if (authToken) { logout(); return; }
  document.getElementById('login-panel').innerHTML =
    '<div class="card" style="margin-top:20px;max-width:360px"><h3>Login</h3><p class="muted" style="margin:8px 0;font-size:0.8rem">Demo account: demo@shop.com / demo123</p>' +
    '<div class="form-group"><label>Email</label><input id="login-email" value="demo@shop.com"></div>' +
    '<div class="form-group"><label>Password</label><input id="login-pass" type="password" value="demo123"></div>' +
    '<button class="btn" onclick="doLogin()" style="width:100%">Log In</button></div>';
  document.getElementById('login-panel').style.display = 'block';
}
async function doLogin() {
  try {
    const data = await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({
      email: document.getElementById('login-email').value,
      password: document.getElementById('login-pass').value
    })});
    authToken = data.token; userName = data.user.name;
    document.getElementById('auth-link').textContent = userName + ' (Logout)';
    document.getElementById('login-panel').style.display = 'none';
    toast('Welcome, ' + userName + '!');
  } catch (e) { toast(e.message); }
}
function logout() {
  authToken = null; userName = null;
  document.getElementById('auth-link').textContent = 'Login';
  document.getElementById('cart-count').style.display = 'none';
  toast('Logged out');
}
loadProducts('', '');
</script>
</body></html>`;
}

function getDemoAccountPage(site: Site | undefined, dark: boolean, backendUrl: string): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - My Account</title>
<meta name="description" content="Account dashboard for ${safeName}. View orders, profile, and manage your account. Ask the AI for help!">
<style>${baseStyles(dark, accent)}</style></head><body>
<div class="container">
  <nav class="nav">
    <div class="nav-brand">\u{1F6CD}\uFE0F ${safeName}</div>
    <div class="nav-links">
      <a href="#">Store</a>
      <a id="auth-link" href="#" onclick="showLogin()">Login</a>
    </div>
  </nav>
  <div id="account-content">
    <div class="card" style="text-align:center;padding:40px">
      <h2>My Account</h2>
      <p class="muted" style="margin:12px 0">Please log in to view your account.</p>
      <p class="muted" style="font-size:0.8rem;margin-bottom:16px">Demo: demo@shop.com / demo123</p>
      <div style="max-width:300px;margin:0 auto">
        <div class="form-group"><label>Email</label><input id="login-email" value="demo@shop.com"></div>
        <div class="form-group"><label>Password</label><input id="login-pass" type="password" value="demo123"></div>
        <button class="btn" onclick="doLogin()" style="width:100%">Log In</button>
      </div>
    </div>
  </div>
  <footer class="footer">Ask the AI assistant to help you view orders or manage your account!</footer>
</div>
<div id="toast-container"></div>
${getWidgetScript(site, dark, backendUrl)}
<script>
const API = ${JSON.stringify(backendUrl + "/api/demo")};
let authToken = null;
function toast(msg) {
  const el = document.createElement('div'); el.className = 'toast'; el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 2600);
}
async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  const r = await fetch(API + path, { ...opts, headers });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
  return r.json();
}
async function doLogin() {
  try {
    const data = await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({
      email: document.getElementById('login-email').value,
      password: document.getElementById('login-pass').value
    })});
    authToken = data.token;
    document.getElementById('auth-link').textContent = data.user.name + ' (Logout)';
    toast('Welcome, ' + data.user.name + '!');
    loadDashboard(data.user);
  } catch (e) { toast(e.message); }
}
async function loadDashboard(user) {
  let ordersHtml = '<p class="muted">No orders yet. Visit the store to place one!</p>';
  try {
    const data = await apiFetch('/orders');
    if (data.orders.length > 0) {
      ordersHtml = '<table><tr><th>Order ID</th><th>Items</th><th>Total</th><th>Status</th><th>Date</th></tr>' +
        data.orders.map(o => '<tr><td><strong>' + o.id + '</strong></td><td>' + o.items.length + ' items</td><td>$' + o.total.toFixed(2) + '</td><td><span class="status-confirmed">' + o.status + '</span></td><td>' + new Date(o.created_at).toLocaleDateString() + '</td></tr>').join('') +
        '</table>';
    }
  } catch (e) {}
  document.getElementById('account-content').innerHTML =
    '<div class="grid" style="grid-template-columns:260px 1fr;gap:20px;margin-top:8px">' +
    '<div class="card"><h3>\u{1F464} Profile</h3><div style="margin-top:12px"><p><strong>' + user.name + '</strong></p><p class="muted" style="font-size:0.85rem">' + user.email + '</p><p class="muted" style="font-size:0.75rem;margin-top:4px">Member since ' + new Date(user.created_at || Date.now()).toLocaleDateString() + '</p></div></div>' +
    '<div><div class="card"><h3>\u{1F4E6} Order History</h3><div style="margin-top:12px">' + ordersHtml + '</div></div></div></div>';
}
function showLogin() {
  if (authToken) { authToken = null; document.getElementById('auth-link').textContent = 'Login'; location.reload(); }
}
</script>
</body></html>`;
}

function getDemoSupportPage(site: Site | undefined, dark: boolean, backendUrl: string): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - Help Center</title>
<meta name="description" content="Help center and FAQ for ${safeName}. Find answers to common questions about shipping, returns, payments. Create support tickets or ask the AI!">
<style>${baseStyles(dark, accent)}</style></head><body>
<div class="container">
  <nav class="nav">
    <div class="nav-brand">\u{1F6CD}\uFE0F ${safeName}</div>
    <div class="nav-links">
      <a href="#">Store</a>
      <a href="#">Account</a>
    </div>
  </nav>
  <div style="text-align:center;padding:32px 0">
    <h1 style="font-size:1.75rem;font-weight:800">Help Center</h1>
    <p class="muted" style="margin-top:8px">Find answers or ask our AI assistant for help!</p>
  </div>
  <div id="faq-section"><h2 class="section-title">\u2753 Frequently Asked Questions</h2><div id="faq-list" class="grid" style="gap:12px"></div></div>
  <div style="margin-top:32px">
    <h2 class="section-title">\u{1F4E9} Submit a Support Ticket</h2>
    <div class="card" style="max-width:500px">
      <div class="form-group"><label>Subject</label><input id="ticket-subject" placeholder="Brief description of your issue"></div>
      <div class="form-group"><label>Message</label><textarea id="ticket-message" rows="4" placeholder="Please describe your issue in detail..."></textarea></div>
      <button class="btn" onclick="submitTicket()">Submit Ticket</button>
      <div id="ticket-result" style="margin-top:12px"></div>
    </div>
  </div>
  <footer class="footer">Need more help? Click the chat bubble and ask the AI assistant anything!</footer>
</div>
<div id="toast-container"></div>
${getWidgetScript(site, dark, backendUrl)}
<script>
const API = ${JSON.stringify(backendUrl + "/api/demo")};
function toast(msg) {
  const el = document.createElement('div'); el.className = 'toast'; el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 2600);
}
async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const r = await fetch(API + path, { ...opts, headers });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
  return r.json();
}
async function loadFAQ() {
  try {
    const data = await apiFetch('/support/faq');
    document.getElementById('faq-list').innerHTML = data.faqs.map(f =>
      '<div class="card" style="cursor:pointer" onclick="this.querySelector(\\'.faq-a\\').style.display=this.querySelector(\\'.faq-a\\').style.display===\\'none\\'?\\'block\\':\\'none\\'">' +
      '<div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:0.9rem">' + f.question + '</strong><span class="muted">\u25BC</span></div>' +
      '<p class="faq-a muted" style="display:none;margin-top:8px;font-size:0.85rem">' + f.answer + '</p></div>'
    ).join('');
  } catch (e) { console.error(e); }
}
async function submitTicket() {
  const subject = document.getElementById('ticket-subject').value;
  const message = document.getElementById('ticket-message').value;
  if (!subject || !message) { toast('Please fill in all fields'); return; }
  try {
    const data = await apiFetch('/support/ticket', { method: 'POST', body: JSON.stringify({ subject, message }) });
    document.getElementById('ticket-result').innerHTML =
      '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px">' +
      '<strong>\u2705 Ticket Created</strong><br><span class="muted" style="font-size:0.85rem">ID: ' + data.ticket.id + ' \u2014 We\\'ll get back to you soon!</span></div>';
    document.getElementById('ticket-subject').value = '';
    document.getElementById('ticket-message').value = '';
    toast('Ticket submitted!');
  } catch (e) { toast(e.message); }
}
loadFAQ();
</script>
</body></html>`;
}

function getDemoBlankPage(site: Site | undefined, dark: boolean): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName}</title>
<style>${baseStyles(dark, accent)} body { display: flex; align-items: center; justify-content: center; min-height: 100vh; }</style></head><body>
<div style="text-align:center">
  <p class="muted">Blank page \u2014 only the chat widget is loaded.</p>
  <p class="muted" style="font-size:0.8rem;margin-top:8px">Click the chat bubble to start a conversation.</p>
</div>
${getWidgetScript(site, dark)}
</body></html>`;
}
