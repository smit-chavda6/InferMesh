import { ArrowDown, ArrowUp } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { MiniSparkline } from "@/components/charts";
import { cn, fmtChangePct } from "@/lib/utils";

export function KpiCard({
  label,
  value,
  sub,
  changePct,
  invertChange,
  sparkline,
}: {
  label: string;
  value: string;
  sub?: string;
  changePct?: number | null;
  /** when true, a positive change is "bad" (e.g. cost, errors) */
  invertChange?: boolean;
  sparkline?: number[];
}) {
  const up = (changePct ?? 0) > 0;
  const good = changePct == null ? null : invertChange ? !up : up;

  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="text-xs font-medium text-text-muted">{label}</div>
      <div className="flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
        {changePct != null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-medium",
              good ? "text-ok" : "text-err",
            )}
          >
            {up ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
            {fmtChangePct(changePct)}
          </span>
        )}
      </div>
      {sub && <div className="text-xs text-text-faint">{sub}</div>}
      {sparkline && sparkline.length > 1 && (
        <div className="-mx-1 mt-1">
          <MiniSparkline data={sparkline} />
        </div>
      )}
    </Card>
  );
}
