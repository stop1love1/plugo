import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getFlows, getFlow, createFlow, updateFlow, deleteFlow,
  addFlowStep, updateFlowStep, deleteFlowStep, reorderFlowSteps,
  type Flow, type FlowStep,
} from "../lib/api";
import {
  Plus, Trash2, X, ChevronUp, ChevronDown,
  Lock, Pencil, GitBranch, Eye, EyeOff,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { useLocale } from "../lib/useLocale";

export default function Flows() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();

  const [showCreate, setShowCreate] = useState(false);
  const [editingFlowId, setEditingFlowId] = useState<string | null>(null);

  // Create form
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newRequiresLogin, setNewRequiresLogin] = useState(false);

  const { data: flows, isLoading } = useQuery({
    queryKey: ["flows", siteId],
    queryFn: () => getFlows(siteId!),
    enabled: !!siteId,
  });

  const createMutation = useMutation({
    mutationFn: createFlow,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["flows", siteId] });
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      setNewRequiresLogin(false);
      setEditingFlowId(data.id);
      toast.success("Flow created");
    },
    onError: () => toast.error("Failed to create flow"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFlow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows", siteId] });
      if (editingFlowId) setEditingFlowId(null);
      toast.success("Flow deleted");
    },
    onError: () => toast.error("Failed to delete flow"),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !siteId) return;
    createMutation.mutate({
      site_id: siteId,
      name: newName.trim(),
      description: newDesc.trim(),
      requires_login: newRequiresLogin,
    });
  };

  return (
    <div>
      <PageHeader title="Flow Guides" subtitle={`${flows?.length || 0} flows`}>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> Add Flow
        </button>
      </PageHeader>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="fixed inset-0 bg-black/40" onClick={() => setShowCreate(false)} />
          <form onSubmit={handleCreate} className="relative bg-white rounded-xl shadow-xl w-full max-w-md p-6 z-10">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg">New Flow Guide</h3>
              <button type="button" onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Flow Name *</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder='e.g. "How to place an order"'
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Brief description of this flow..."
                  rows={2}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={newRequiresLogin}
                  onChange={(e) => setNewRequiresLogin(e.target.checked)}
                  className="rounded border-gray-300"
                />
                <Lock className="w-3.5 h-3.5" />
                Requires user login
              </label>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="text-gray-500 px-4 py-2 hover:bg-gray-100 rounded-lg">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={createMutation.isPending || !newName.trim()} className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {createMutation.isPending ? t("common.loading") : "Create"}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Flow editor */}
      {editingFlowId && (
        <FlowEditor
          flowId={editingFlowId}
          siteId={siteId!}
          onClose={() => {
            setEditingFlowId(null);
            queryClient.invalidateQueries({ queryKey: ["flows", siteId] });
          }}
        />
      )}

      {/* Flow list */}
      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : !flows?.length ? (
        <EmptyState icon={GitBranch} message="No flow guides yet. Create one to teach your bot website flows." />
      ) : (
        <div className="space-y-3">
          {flows.map((flow) => (
            <div key={flow.id} className="bg-white p-4 rounded-xl border border-gray-200 hover:border-gray-300 transition-colors">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium text-gray-900">{flow.name}</h4>
                    {flow.requires_login && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-xs">
                        <Lock className="w-3 h-3" /> Login required
                      </span>
                    )}
                    {!flow.is_enabled && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-xs">
                        <EyeOff className="w-3 h-3" /> Disabled
                      </span>
                    )}
                  </div>
                  {flow.description && (
                    <p className="text-sm text-gray-500 mt-1">{flow.description}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    {flow.step_count || 0} steps
                  </p>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setEditingFlowId(flow.id)}
                    className="text-gray-400 hover:text-primary-600 p-1.5 rounded-lg hover:bg-gray-50"
                    title="Edit flow"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm("Delete this flow?")) deleteMutation.mutate(flow.id);
                    }}
                    className="text-gray-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-gray-50"
                    title="Delete flow"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ============================================================
// Flow Editor (inline modal)
// ============================================================

function FlowEditor({ flowId, siteId, onClose }: { flowId: string; siteId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  const [newStepTitle, setNewStepTitle] = useState("");
  const [newStepDesc, setNewStepDesc] = useState("");
  const [newStepUrl, setNewStepUrl] = useState("");

  const { data: flow, isLoading } = useQuery({
    queryKey: ["flow", flowId],
    queryFn: () => getFlow(flowId),
  });

  const updateMutation = useMutation({
    mutationFn: ({ data }: { data: Partial<Flow> }) => updateFlow(flowId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", flowId] });
      toast.success("Flow updated");
    },
    onError: () => toast.error("Failed to update"),
  });

  const addStepMutation = useMutation({
    mutationFn: (data: { title: string; description?: string; url?: string }) => addFlowStep(flowId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", flowId] });
      setNewStepTitle("");
      setNewStepDesc("");
      setNewStepUrl("");
      toast.success("Step added");
    },
    onError: () => toast.error("Failed to add step"),
  });

  const updateStepMutation = useMutation({
    mutationFn: ({ stepId, data }: { stepId: string; data: Partial<FlowStep> }) => updateFlowStep(stepId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", flowId] });
    },
    onError: () => toast.error("Failed to update step"),
  });

  const deleteStepMutation = useMutation({
    mutationFn: deleteFlowStep,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", flowId] });
      toast.success("Step deleted");
    },
    onError: () => toast.error("Failed to delete step"),
  });

  const reorderMutation = useMutation({
    mutationFn: (stepIds: string[]) => reorderFlowSteps(flowId, stepIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", flowId] });
    },
  });

  const steps = flow?.steps || [];

  const moveStep = (index: number, direction: "up" | "down") => {
    const newSteps = [...steps];
    const swapIdx = direction === "up" ? index - 1 : index + 1;
    if (swapIdx < 0 || swapIdx >= newSteps.length) return;
    [newSteps[index], newSteps[swapIdx]] = [newSteps[swapIdx], newSteps[index]];
    reorderMutation.mutate(newSteps.map((s) => s.id));
  };

  const handleAddStep = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStepTitle.trim()) return;
    addStepMutation.mutate({
      title: newStepTitle.trim(),
      description: newStepDesc.trim() || undefined,
      url: newStepUrl.trim() || undefined,
    });
  };

  if (isLoading) return <div className="text-gray-400 py-8 text-center">{t("common.loading")}</div>;
  if (!flow) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col z-10">
        {/* Header */}
        <div className="flex items-center justify-between p-6 pb-4 border-b border-gray-100 shrink-0">
          <div className="flex-1 min-w-0">
            <input
              defaultValue={flow.name}
              onBlur={(e) => {
                const val = e.target.value.trim();
                if (val && val !== flow.name) updateMutation.mutate({ data: { name: val } });
              }}
              className="text-lg font-semibold text-gray-900 w-full bg-transparent border-none outline-none focus:ring-0 p-0"
            />
            <input
              defaultValue={flow.description}
              onBlur={(e) => {
                const val = e.target.value.trim();
                if (val !== flow.description) updateMutation.mutate({ data: { description: val } });
              }}
              placeholder="Add a description..."
              className="text-sm text-gray-500 w-full bg-transparent border-none outline-none focus:ring-0 p-0 mt-1"
            />
          </div>
          <div className="flex items-center gap-2 ml-4 shrink-0">
            <label className="flex items-center gap-1.5 text-xs text-gray-500">
              <input
                type="checkbox"
                checked={flow.requires_login}
                onChange={(e) => updateMutation.mutate({ data: { requires_login: e.target.checked } })}
                className="rounded border-gray-300"
              />
              <Lock className="w-3 h-3" /> Login
            </label>
            <label className="flex items-center gap-1.5 text-xs text-gray-500">
              <input
                type="checkbox"
                checked={flow.is_enabled}
                onChange={(e) => updateMutation.mutate({ data: { is_enabled: e.target.checked } })}
                className="rounded border-gray-300"
              />
              <Eye className="w-3 h-3" /> Enabled
            </label>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Steps */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {steps.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">No steps yet. Add your first step below.</p>
          )}

          {steps.map((step, idx) => (
            <StepCard
              key={step.id}
              step={step}
              index={idx}
              total={steps.length}
              onMoveUp={() => moveStep(idx, "up")}
              onMoveDown={() => moveStep(idx, "down")}
              onUpdate={(data) => updateStepMutation.mutate({ stepId: step.id, data })}
              onDelete={() => deleteStepMutation.mutate(step.id)}
            />
          ))}

          {/* Add step form */}
          <form onSubmit={handleAddStep} className="bg-gray-50 rounded-lg p-4 border border-dashed border-gray-300">
            <p className="text-xs font-medium text-gray-500 mb-3">+ Add Step {steps.length + 1}</p>
            <div className="space-y-2">
              <input
                value={newStepTitle}
                onChange={(e) => setNewStepTitle(e.target.value)}
                placeholder="Step title (e.g. Click the cart icon)"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
              />
              <textarea
                value={newStepDesc}
                onChange={(e) => setNewStepDesc(e.target.value)}
                placeholder="Detailed instructions (optional)"
                rows={2}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
              />
              <input
                value={newStepUrl}
                onChange={(e) => setNewStepUrl(e.target.value)}
                placeholder="Page URL (optional)"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={addStepMutation.isPending || !newStepTitle.trim()}
                  className="bg-primary-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50"
                >
                  {addStepMutation.isPending ? t("common.loading") : "Add Step"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// Step Card
// ============================================================

function StepCard({
  step, index, total, onMoveUp, onMoveDown, onUpdate, onDelete,
}: {
  step: FlowStep;
  index: number;
  total: number;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onUpdate: (data: Partial<FlowStep>) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(step.title);
  const [desc, setDesc] = useState(step.description);
  const [url, setUrl] = useState(step.url || "");

  const handleSave = () => {
    onUpdate({
      title: title.trim() || step.title,
      description: desc.trim(),
      url: url.trim() || null,
    });
    setEditing(false);
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <div className="flex items-start gap-2">
        {/* Reorder buttons */}
        <div className="flex flex-col items-center gap-0.5 pt-1">
          <button onClick={onMoveUp} disabled={index === 0} className="text-gray-300 hover:text-gray-500 disabled:opacity-30">
            <ChevronUp className="w-4 h-4" />
          </button>
          <span className="text-xs font-medium text-gray-400 w-5 text-center">{step.step_order}</span>
          <button onClick={onMoveDown} disabled={index === total - 1} className="text-gray-300 hover:text-gray-500 disabled:opacity-30">
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="space-y-2">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full border border-gray-300 rounded px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-primary-500"
                autoFocus
              />
              <textarea
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="Instructions..."
                rows={2}
                className="w-full border border-gray-300 rounded px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-primary-500"
              />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="URL"
                className="w-full border border-gray-300 rounded px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-primary-500"
              />
              <div className="flex gap-2">
                <button onClick={handleSave} className="text-xs bg-primary-600 text-white px-3 py-1 rounded hover:bg-primary-700">Save</button>
                <button onClick={() => setEditing(false)} className="text-xs text-gray-500 hover:text-gray-700">Cancel</button>
              </div>
            </div>
          ) : (
            <>
              <p className="text-sm font-medium text-gray-900">{step.title}</p>
              {step.description && <p className="text-xs text-gray-500 mt-0.5">{step.description}</p>}
              {step.url && (
                <p className="text-xs text-primary-600 mt-0.5 truncate">{step.url}</p>
              )}
            </>
          )}
        </div>

        {/* Actions */}
        {!editing && (
          <div className="flex gap-0.5 shrink-0">
            <button onClick={() => setEditing(true)} className="text-gray-400 hover:text-primary-600 p-1">
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button onClick={onDelete} className="text-gray-400 hover:text-red-500 p-1">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
