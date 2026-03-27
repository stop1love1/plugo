import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSites, createSite } from "../lib/api";
import { Plus, Globe, ArrowRight } from "lucide-react";

export default function Sites() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");

  const { data: sites = [], isLoading } = useQuery({
    queryKey: ["sites"],
    queryFn: getSites,
  });

  const mutation = useMutation({
    mutationFn: createSite,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      setShowCreate(false);
      setName("");
      setUrl("");
      navigate(`/site/${data.id}/setup`);
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !url) return;
    mutation.mutate({ name, url });
  };

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sites</h1>
          <p className="text-gray-500 mt-1">Quản lý các website đã kết nối với Plugo</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> Thêm Site
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold text-lg mb-4">Tạo Site mới</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tên website</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Website"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              />
            </div>
            <div className="flex gap-3">
              <button type="submit" disabled={mutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700">
                {mutation.isPending ? "Đang tạo..." : "Tạo Site"}
              </button>
              <button type="button" onClick={() => setShowCreate(false)} className="text-gray-500 px-4 py-2">
                Huỷ
              </button>
            </div>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-gray-400">Đang tải...</div>
      ) : sites.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
          <Globe className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">Chưa có site nào. Nhấn "Thêm Site" để bắt đầu.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {sites.map((site: any) => (
            <div
              key={site.id}
              onClick={() => navigate(`/site/${site.id}/setup`)}
              className="bg-white p-5 rounded-xl border border-gray-200 hover:border-primary-300 hover:shadow-sm cursor-pointer transition-all flex items-center justify-between"
            >
              <div>
                <h3 className="font-semibold text-gray-900">{site.name}</h3>
                <p className="text-sm text-gray-500 mt-1">{site.url}</p>
                <p className="text-xs text-gray-400 mt-1">Token: {site.token.substring(0, 12)}...</p>
              </div>
              <ArrowRight className="w-5 h-5 text-gray-400" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
