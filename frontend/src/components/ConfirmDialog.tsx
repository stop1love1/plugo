import { useEffect, useRef, useCallback } from "react";
import { AlertTriangle } from "lucide-react";
import { useLocale } from "../lib/useLocale";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  danger = true,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useLocale();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  // Focus trap and Escape key handler
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }

      // Focus trap: Tab within dialog
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    },
    [open, onCancel]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      // Auto-focus cancel button when dialog opens
      cancelBtnRef.current?.focus();
    }
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/40" onClick={onCancel} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative bg-white rounded-xl shadow-xl max-w-sm w-full p-6"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className={`p-2 rounded-lg ${danger ? "bg-red-50" : "bg-blue-50"}`}>
            <AlertTriangle className={`w-5 h-5 ${danger ? "text-red-600" : "text-blue-600"}`} />
          </div>
          <div>
            <h3 id="confirm-dialog-title" className="font-semibold text-gray-900">{title}</h3>
            <p className="text-sm text-gray-600 mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button
            ref={cancelBtnRef}
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-lg"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-sm text-white rounded-lg disabled:opacity-50 ${
              danger ? "bg-red-600 hover:bg-red-700" : "bg-primary-600 hover:bg-primary-700"
            }`}
          >
            {loading ? t("common.loading") : confirmLabel || t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
