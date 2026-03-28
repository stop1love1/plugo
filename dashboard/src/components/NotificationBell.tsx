import { useState, useEffect, useCallback } from "react";
import { Bell, X, CheckCircle, XCircle, Trash2 } from "lucide-react";
import { useLocale } from "../lib/useLocale";

export type Notification = {
  id: string;
  type: "success" | "error" | "info";
  title: string;
  message?: string;
  timestamp: number;
  read: boolean;
};

const STORAGE_KEY = "plugo_notifications";

function loadNotifications(): Notification[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveNotifications(notifications: Notification[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notifications.slice(0, 50)));
}

// Global function to push notifications from anywhere
let pushNotificationFn: ((n: Omit<Notification, "id" | "timestamp" | "read">) => void) | null = null;

export function pushNotification(n: Omit<Notification, "id" | "timestamp" | "read">) {
  pushNotificationFn?.(n);
}

export function NotificationBell() {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>(loadNotifications);

  const addNotification = useCallback((n: Omit<Notification, "id" | "timestamp" | "read">) => {
    const newNotif: Notification = {
      ...n,
      id: Date.now().toString(),
      timestamp: Date.now(),
      read: false,
    };
    setNotifications((prev) => {
      const next = [newNotif, ...prev].slice(0, 50);
      saveNotifications(next);
      return next;
    });
  }, []);

  useEffect(() => {
    pushNotificationFn = addNotification;
    return () => { pushNotificationFn = null; };
  }, [addNotification]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markAllRead = () => {
    setNotifications((prev) => {
      const next = prev.map((n) => ({ ...n, read: true }));
      saveNotifications(next);
      return next;
    });
  };

  const clearAll = () => {
    setNotifications([]);
    saveNotifications([]);
  };

  const removeOne = (id: string) => {
    setNotifications((prev) => {
      const next = prev.filter((n) => n.id !== id);
      saveNotifications(next);
      return next;
    });
  };

  return (
    <div className="relative">
      <button
        onClick={() => {
          setOpen(!open);
          if (!open) markAllRead();
        }}
        className="relative p-1 text-gray-400 hover:text-gray-600"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[10px] flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-8 z-50 w-80 bg-white rounded-xl border border-gray-200 shadow-lg">
            <div className="flex items-center justify-between p-3 border-b border-gray-100">
              <span className="font-medium text-sm">{t("notifications.title")}</span>
              {notifications.length > 0 && (
                <button onClick={clearAll} className="text-xs text-gray-400 hover:text-gray-600">
                  {t("notifications.clearAll")}
                </button>
              )}
            </div>
            <div className="max-h-64 overflow-y-auto">
              {notifications.length === 0 ? (
                <p className="p-4 text-sm text-gray-400 text-center">{t("notifications.empty")}</p>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className={`flex items-start gap-2 p-3 border-b border-gray-50 last:border-0 ${!n.read ? "bg-blue-50/30" : ""}`}
                  >
                    {n.type === "success" ? (
                      <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                    ) : n.type === "error" ? (
                      <XCircle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                    ) : (
                      <Bell className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-700">{n.title}</p>
                      {n.message && <p className="text-xs text-gray-500">{n.message}</p>}
                      <p className="text-[10px] text-gray-300 mt-0.5">
                        {new Date(n.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                    <button onClick={() => removeOne(n.id)} className="text-gray-300 hover:text-gray-500">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
