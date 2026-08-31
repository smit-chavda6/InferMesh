import { Badge } from "@/components/ui/primitives";

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
  return <span className="font-medium capitalize">{provider}</span>;
}
