import { X } from "lucide-react";
import type { FileUploadProgress } from "./types";

interface UploadProgressListProps {
  items: FileUploadProgress[];
  onDismiss: (id: string) => void;
  onRetry?: (id: string) => void;
  compact?: boolean;
}

export function UploadProgressList({ items, onDismiss, onRetry, compact = false }: UploadProgressListProps) {
  if (items.length === 0) return null;

  return (
    <div className="flex-none max-h-48 overflow-y-auto border-b border-gray-800">
      {items.map((item) => {
        const failed = item.state === "error";
        return (
          <div
            key={item.id}
            className={`${compact ? "px-6" : "px-3"} py-3 border-b last:border-b-0 text-xs flex items-start gap-3 ${
              failed
                ? "bg-rose-950/80 border-rose-800 text-rose-200"
                : "bg-emerald-950/80 border-emerald-800 text-emerald-200"
            }`}
          >
            <div className="space-y-1.5 flex-1 min-w-0 max-w-xl">
              <div className="flex items-center justify-between gap-4 font-semibold">
                <span className="truncate" title={item.fileName}>{item.fileName}</span>
                <span className="shrink-0">{item.percent}%</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="truncate" title={item.error || item.message}>
                  {item.error || item.message || "Preparing upload"}
                </span>
                {item.totalWorkspaces ? (
                  <span className="shrink-0 opacity-80">
                    {item.completedWorkspaces ?? 0}/{item.totalWorkspaces} completed
                  </span>
                ) : null}
              </div>
              <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-200 ${failed ? "bg-rose-400" : "bg-emerald-400"}`}
                  style={{ width: `${item.percent}%` }}
                />
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {failed && item.retryable && onRetry ? (
                <button
                  type="button"
                  onClick={() => onRetry(item.id)}
                  className="px-2 py-1 rounded font-semibold text-rose-100 border border-rose-700 hover:bg-rose-900 transition"
                  aria-label={`Retry upload for ${item.fileName}`}
                >
                  Retry
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => onDismiss(item.id)}
                className={`p-1 rounded transition ${
                  failed ? "text-rose-300 hover:bg-rose-900 hover:text-white" : "text-emerald-300 hover:bg-emerald-900 hover:text-white"
                }`}
                aria-label={`Dismiss upload progress for ${item.fileName}`}
                title="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
