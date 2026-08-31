import { useState } from "react";
import { Pause, Play } from "lucide-react";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { EmptyState, ErrorState, LoadingRows } from "@/components/States";
import { useLiveRequests } from "@/api/queries";
import { fmtMs } from "@/lib/utils";

export function LiveActivityPage() {
  const [paused, setPaused] = useState(false);
  const q = useLiveRequests(!paused);

  return (
    <div>
      <PageHeader
        title="Live Activity"
        description="Most recent requests through the gateway. Polls every few seconds while live."
        actions={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium">
              <StatusDot status={paused ? "disabled" : "healthy"} pulse={!paused} />
              {paused ? "Paused" : "LIVE"}
            </span>
            <Button size="sm" variant="outline" onClick={() => setPaused((p) => !p)}>
              {paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
              {paused ? "Resume" : "Pause"}
            </Button>
          </div>
        }
      />

      <Card className="p-0">
        {q.isLoading ? (
          <div className="p-4">
            <LoadingRows rows={10} />
          </div>
        ) : q.isError ? (
          <div className="p-4">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </div>
        ) : !q.data?.items.length ? (
          <div className="p-4">
            <EmptyState title="No requests in the last hour" />
          </div>
        ) : (
          <ul className="divide-y divide-border font-mono text-xs">
            {q.data.items.map((r) => (
              <li key={r.request_id} className="flex items-center gap-3 px-4 py-2 animate-in">
                <span className="w-20 text-text-faint">
                  {new Date(r.created_at).toLocaleTimeString("en-US", { hour12: false })}
                </span>
                <span className="w-24 capitalize">{r.provider}</span>
                <span className="w-28">
                  {r.status === "error" ? (
                    <Badge tone="err">ERROR</Badge>
                  ) : r.fallback_used ? (
                    <Badge tone="warn">FALLBACK</Badge>
                  ) : (
                    <Badge tone="ok">SUCCESS</Badge>
                  )}
                </span>
                <span className="w-20 text-right tabular-nums">{fmtMs(r.latency_ms)}</span>
                <span className="ml-2 hidden truncate text-text-faint sm:block">{r.model}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
