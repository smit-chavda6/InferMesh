import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/primitives";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/States";
import { useRateLimits } from "@/api/queries";
import { cn, fmtDateTime, fmtInt } from "@/lib/utils";

export function RateLimitsPage() {
  const q = useRateLimits();

  return (
    <div>
      <PageHeader
        title="Rate Limits"
        description="Redis sliding-window limiter, per API key. Live current-usage counters refresh every 10s."
      />

      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <>
          <div className="mb-4 text-xs text-text-muted">
            Anonymous callers: <span className="font-medium text-text">{q.data.anon_limit_per_minute}</span> req/min shared bucket.
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Per-project usage</CardTitle>
            </CardHeader>
            <CardContent>
              {!q.data.projects.length ? (
                <EmptyState title="No projects yet" hint="Create an API key on the API Keys page." />
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Project</TH>
                      <TH className="text-right">Limit</TH>
                      <TH className="text-right">Current</TH>
                      <TH className="text-right">Remaining</TH>
                      <TH>Usage</TH>
                      <TH>Status</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {q.data.projects.map((p) => {
                      const pct = p.limit ? Math.min(100, (p.current / p.limit) * 100) : 0;
                      return (
                        <TR key={p.project_id}>
                          <TD className="font-medium">{p.project}</TD>
                          <TD className="text-right tabular-nums">{fmtInt(p.limit)}/min</TD>
                          <TD className="text-right tabular-nums">{fmtInt(p.current)}</TD>
                          <TD className="text-right tabular-nums">{fmtInt(p.remaining)}</TD>
                          <TD className="w-40">
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-subtle">
                              <div
                                className={cn(
                                  "h-full rounded-full",
                                  pct > 90 ? "bg-err" : pct > 70 ? "bg-warn" : "bg-accent",
                                )}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </TD>
                          <TD>
                            <Badge tone={p.status === "active" ? "ok" : "err"}>{p.status}</Badge>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Recent 429 events</CardTitle>
            </CardHeader>
            <CardContent>
              {!q.data.recent_429.length ? (
                <EmptyState title="No rate-limit rejections recently" />
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Time</TH>
                      <TH>Project</TH>
                      <TH>API key</TH>
                      <TH>Request</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {q.data.recent_429.map((e) => (
                      <TR key={e.request_id}>
                        <TD className="text-text-muted">{fmtDateTime(e.created_at)}</TD>
                        <TD>{e.project_name ?? "anonymous"}</TD>
                        <TD className="font-mono text-xs text-text-muted">{e.api_key_prefix ?? "—"}</TD>
                        <TD className="font-mono text-xs text-text-muted">{e.request_id.slice(0, 16)}…</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
