import { RANGES, useRange } from "@/hooks/useRange";
import { cn } from "@/lib/utils";
import type { RangeKey } from "@/api/types";

const LABEL: Record<RangeKey, string> = { "1h": "1h", "24h": "24h", "7d": "7d", "30d": "30d" };

export function RangePicker() {
  const [range, setRange] = useRange();
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-border">
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => setRange(r)}
          className={cn(
            "px-3 py-1.5 text-xs font-medium transition-colors",
            r === range ? "bg-accent text-accent-fg" : "bg-panel text-text-muted hover:bg-bg-subtle",
          )}
        >
          {LABEL[r]}
        </button>
      ))}
    </div>
  );
}
