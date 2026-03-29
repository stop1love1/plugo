import { type LucideIcon } from "lucide-react";

type EmptyStateProps = {
  icon: LucideIcon;
  message: string;
};

export function EmptyState({ icon: Icon, message }: EmptyStateProps) {
  return (
    <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
      <Icon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
      <p className="text-gray-500">{message}</p>
    </div>
  );
}
