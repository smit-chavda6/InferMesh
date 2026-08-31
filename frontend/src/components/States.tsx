import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { Button, Skeleton } from "@/components/ui/primitives";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";

export function LoadingCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-[104px]" />
      ))}
    </div>
  );
}

export function LoadingBlock({ className }: { className?: string }) {
  return <Skeleton className={cn("h-64 w-full", className)} />;
}

export function LoadingRows({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Something went wrong.";
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-border bg-panel p-10 text-center">
      <AlertTriangle className="size-6 text-err" />
      <div>
        <div className="text-sm font-medium">Couldn't load this data</div>
        <div className="mt-1 text-xs text-text-muted">{msg}</div>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-3.5" /> Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  hint,
  action,
}: {
  title?: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-panel p-12 text-center">
      <Inbox className="size-6 text-text-faint" />
      <div>
        <div className="text-sm font-medium">{title}</div>
        {hint && <div className="mt-1 text-xs text-text-muted">{hint}</div>}
      </div>
      {action}
    </div>
  );
}
