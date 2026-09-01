import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { CircuitBadge } from "@/components/badges";
import { ErrorState, LoadingBlock } from "@/components/States";
import { useSystemHealth } from "@/api/queries";
import { fmtDateTime, fmtMs, fmtPct, providerLabel } from "@/lib/utils";

const LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
};

const depLabel = (key: string) => LABELS[key] ?? providerLabel(key);

export function SystemHealthPage() {
  const q = useSystemHealth();

  return (
    <div>
      <PageHeader
        title="System Health"
        description="Gateway and every dependency. Refreshes every 15s."
      />

      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Line name="Gateway" status={q.data.gateway.status} />
              {Object.entries(q.data.dependencies).map(([key, d]) => (
                <Line
                  key={key}
                  name={depLabel(key)}
                  status={d.status}
                  detail={
                    <>
                      <CircuitBadge state={d.circuit_state} />
                      {d.latency_ms != null && <span>{fmtMs(d.latency_ms)}</span>}
                      {d.avg_latency_ms != null && <span>avg {fmtMs(d.avg_latency_ms)}</span>}
                      {d.success_rate != null && <span>{fmtPct(d.success_rate)} ok</span>}
                      <span className="text-text-faint">{fmtDateTime(d.checked_at)}</span>
                    </>
                  }
                />
              ))}
            </CardContent>
          </Card>

          {/* dependency graph */}
          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Dependency graph</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-3 text-sm">
                <Node label="Gateway" status={q.data.gateway.status} />
                <span className="text-text-faint">→</span>
                <div className="flex flex-col gap-2">
                  {Object.entries(q.data.dependencies).map(([key, d]) => (
                    <Node key={key} label={depLabel(key)} status={d.status} />
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function Line({
  name,
  status,
  detail,
}: {
  name: string;
  status: string;
  detail?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5 text-sm">
      <div className="flex w-40 items-center gap-2 font-medium capitalize">
        <StatusDot status={status} />
        {name}
      </div>
      <span className="w-24 capitalize text-text-muted">{status}</span>
      <div className="ml-auto flex flex-wrap items-center gap-3 text-xs text-text-muted">{detail}</div>
    </div>
  );
}

function Node({ label, status }: { label: string; status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-1">
      <StatusDot status={status} />
      {label}
    </span>
  );
}
