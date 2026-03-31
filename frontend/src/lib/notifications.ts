export type Notification = {
  id: string;
  type: "success" | "error" | "info";
  title: string;
  message?: string;
  timestamp: number;
  read: boolean;
};

const STORAGE_KEY = "plugo_notifications";
export const NOTIFICATIONS_CHANGE_EVENT = "plugo-notifications-change";

export function loadNotifications(): Notification[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function persistNotifications(notifications: Notification[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notifications.slice(0, 50)));
  window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGE_EVENT));
}

export function pushNotification(n: Omit<Notification, "id" | "timestamp" | "read">) {
  const newNotif: Notification = {
    ...n,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    timestamp: Date.now(),
    read: false,
  };
  const next = [newNotif, ...loadNotifications()].slice(0, 50);
  persistNotifications(next);
}

export function markAllNotificationsRead() {
  const next = loadNotifications().map((x) => ({ ...x, read: true }));
  persistNotifications(next);
}

export function clearAllNotifications() {
  persistNotifications([]);
}

export function removeNotification(id: string) {
  const next = loadNotifications().filter((n) => n.id !== id);
  persistNotifications(next);
}

export function subscribeNotifications(listener: () => void) {
  const fn = () => listener();
  window.addEventListener(NOTIFICATIONS_CHANGE_EVENT, fn);
  return () => window.removeEventListener(NOTIFICATIONS_CHANGE_EVENT, fn);
}
