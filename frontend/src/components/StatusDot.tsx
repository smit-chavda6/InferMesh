import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/api/types";

const TONE: Record<string, string> = {
  healthy: "bg-ok",
  degraded: "bg-warn",
  unhealthy: "bg-err",
  disabled: "bg-text-faint",
  unknown: "bg-text-faint",
  active: "bg-ok",
  revoked: "bg-err",
};

export function StatusDot({
  status,
  pulse,
  className,
}: {
  status: HealthStatus | string;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex size-2 shrink-0", className)}>
      {pulse && status === "healthy" && (
        <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", TONE[status])} />
      )}
      <span className={cn("relative inline-flex size-2 rounded-full", TONE[status] ?? "bg-text-faint")} />
    </span>
  );
}

export function StatusLabel({ status }: { status: HealthStatus | string }) {
  return (
    <span className="inline-flex items-center gap-1.5 capitalize">
      <StatusDot status={status} />
      {status}
    </span>
  );
}
