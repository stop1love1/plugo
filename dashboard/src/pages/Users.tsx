import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getUsers, createUser, updateUserRole, deleteUser, getErrorMessage } from "../lib/api";
import { Users as UsersIcon, Plus, Trash2, Shield, Eye, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { FormField } from "../components/FormField";
import { EmptyState } from "../components/EmptyState";
import { useLocale } from "../lib/useLocale";
import { SkeletonTable } from "../components/Skeleton";
import { ConfirmDialog } from "../components/ConfirmDialog";

export default function UsersPage() {
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", role: "viewer" });
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [pendingRoleChange, setPendingRoleChange] = useState<{ id: string; username: string; role: string } | null>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showAdd) firstInputRef.current?.focus();
  }, [showAdd]);

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: getUsers,
  });

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowAdd(false);
      setForm({ username: "", password: "", role: "viewer" });
      toast.success("User created");
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err)),
  });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) => updateUserRole(id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("Role updated");
    },
    onError: () => toast.error("Failed to update role"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("User deleted");
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err)),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.username || !form.password) return;
    createMutation.mutate(form);
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title={t("users.title")} subtitle={t("users.subtitle")}>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> {t("users.addUser")}
        </button>
      </PageHeader>

      {showAdd && (
        <form onSubmit={handleCreate} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">{t("users.addUser")}</h3>
            <button type="button" onClick={() => setShowAdd(false)} className="text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <FormField label={t("users.username")}>
              <input ref={firstInputRef} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="username" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label={t("login.password")}>
              <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                type="password" placeholder="min 8 chars" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label={t("users.role")}>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none">
                <option value="admin">Admin</option>
                <option value="viewer">Viewer</option>
              </select>
            </FormField>
          </div>
          <div className="flex gap-3 mt-4">
            <button type="submit" disabled={createMutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg">
              {createMutation.isPending ? t("common.loading") : t("common.save")}
            </button>
            <button type="button" onClick={() => setShowAdd(false)} className="text-gray-500 px-4 py-2">{t("common.cancel")}</button>
          </div>
        </form>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t("common.delete")}
        message={t("users.deleteConfirm")}
        danger
        loading={deleteMutation.isPending}
        onConfirm={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget); setDeleteTarget(null); }}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={!!pendingRoleChange}
        title={t("users.role")}
        message={`Change role of ${pendingRoleChange?.username ?? ""} to ${pendingRoleChange?.role ?? ""}?`}
        loading={roleMutation.isPending}
        onConfirm={() => { if (pendingRoleChange) roleMutation.mutate({ id: pendingRoleChange.id, role: pendingRoleChange.role }); setPendingRoleChange(null); }}
        onCancel={() => setPendingRoleChange(null)}
      />

      {isLoading ? (
        <SkeletonTable rows={3} />
      ) : users.length === 0 ? (
        <EmptyState icon={UsersIcon} message={t("users.noUsers")} />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-gray-500 border-b bg-gray-50">
                <th className="px-4 py-3">{t("users.username")}</th>
                <th className="px-4 py-3">{t("users.role")}</th>
                <th className="px-4 py-3">{t("users.createdAt")}</th>
                <th className="px-4 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((user: any) => (
                <tr key={user.id} className="border-b border-gray-50 last:border-0">
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{user.username}</span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={user.role}
                      onChange={(e) => setPendingRoleChange({ id: user.id, username: user.username, role: e.target.value })}
                      className="text-xs border rounded px-2 py-1 outline-none"
                    >
                      <option value="admin">Admin</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {user.created_at ? new Date(user.created_at).toLocaleDateString() : ""}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setDeleteTarget(user.id)}
                      className="text-gray-400 hover:text-red-500 p-1"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
