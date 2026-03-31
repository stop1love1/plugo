import { useState, useEffect, useCallback } from "react";
import {
  loadNotifications,
  subscribeNotifications,
  markAllNotificationsRead,
  clearAllNotifications,
  removeNotification,
  type Notification,
} from "./notifications";

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>(loadNotifications);

  const refresh = useCallback(() => setNotifications(loadNotifications()), []);

  useEffect(() => subscribeNotifications(refresh), [refresh]);

  const markAllRead = useCallback(() => markAllNotificationsRead(), []);
  const clearAll = useCallback(() => clearAllNotifications(), []);
  const removeOne = useCallback((id: string) => removeNotification(id), []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return {
    notifications,
    unreadCount,
    markAllRead,
    clearAll,
    removeOne,
  };
}
