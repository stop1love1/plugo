export function SkeletonLine({ width = "100%", height = "16px" }: { width?: string; height?: string }) {
  return (
    <div
      className="animate-pulse bg-gray-200 rounded"
      style={{ width, height }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-white p-5 rounded-xl border border-gray-200 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-gray-200 rounded-lg" />
        <div className="flex-1">
          <div className="h-6 bg-gray-200 rounded w-16 mb-1" />
          <div className="h-4 bg-gray-200 rounded w-24" />
        </div>
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-pulse">
      <div className="h-10 bg-gray-50 border-b" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-gray-50 last:border-0">
          <div className="h-4 bg-gray-200 rounded flex-1" />
          <div className="h-4 bg-gray-200 rounded w-20" />
          <div className="h-4 bg-gray-200 rounded w-16" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonList({ items = 4 }: { items?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="bg-white p-4 rounded-xl border border-gray-200 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-200 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart() {
  return (
    <div className="bg-white p-6 rounded-xl border border-gray-200 animate-pulse">
      <div className="h-5 bg-gray-200 rounded w-40 mb-4" />
      <div className="h-64 bg-gray-100 rounded-lg flex items-end justify-around px-4 pb-4 gap-2">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="bg-gray-200 rounded-t w-full"
            style={{ height: `${20 + Math.random() * 60}%` }}
          />
        ))}
      </div>
    </div>
  );
}
