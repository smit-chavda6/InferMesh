import { Badge } from "@/components/ui/primitives";
import { providerLabel } from "@/lib/utils";
import type { CircuitState } from "@/api/types";

export function StatusBadge({ status }: { status: "success" | "error" | string }) {
  return <Badge tone={status === "success" ? "ok" : "err"}>{status}</Badge>;
}

export function CacheBadge({ status }: { status: "HIT" | "MISS" | "DISABLED" | string }) {
  if (status === "HIT") return <Badge tone="accent">HIT</Badge>;
  if (status === "MISS") return <Badge tone="neutral">MISS</Badge>;
  return <Badge tone="neutral">—</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === "critical" ? "err" : severity === "warning" ? "warn" : "info";
  return <Badge tone={tone}>{severity}</Badge>;
}

export function ProviderTag({ provider }: { provider: string }) {
  return <span className="font-medium">{providerLabel(provider)}</span>;
}

/** Circuit breaker state — nothing shown while the circuit is closed (the norm). */
export function CircuitBadge({
  state,
  retryIn,
}: {
  state: CircuitState | undefined;
  retryIn?: number;
}) {
  if (!state || state === "closed") return null;
  if (state === "half_open") return <Badge tone="warn">circuit half-open</Badge>;
  return (
    <Badge tone="err">
      circuit open{retryIn ? ` · retry ${Math.ceil(retryIn)}s` : ""}
    </Badge>
  );
}
