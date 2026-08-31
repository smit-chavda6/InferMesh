import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { RangePicker } from "@/components/RangePicker";
import { BarByGroup, DonutByGroup } from "@/components/charts";
import { StatusDot } from "@/components/StatusDot";
import { EmptyState, ErrorState, LoadingBlock, LoadingCards } from "@/components/States";
import { useProviderHealth, useProviders } from "@/api/queries";
import { useRange } from "@/hooks/useRange";
import { cn, fmtInt, fmtMs, fmtPct, fmtUsd, providerLabel } from "@/lib/utils";

export function ProvidersPage() {
  const [range] = useRange();
  const q = useProviders(range);
  const health = useProviderHealth();
  const healthByName = Object.fromEntries((health.data?.providers ?? []).map((h) => [h.provider, h]));

  return (
    <div>
      <PageHeader
        title="Providers"
        description="Per-provider volume, cost, latency, error rate and routing configuration."
        actions={<RangePicker />}
      />

      {q.isLoading ? (
        <LoadingCards count={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <>
          {/* comparison charts */}
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Requests by provider</CardTitle>
              </CardHeader>
              <CardContent>
                <DonutByGroup data={q.data.providers} labelKey="provider" valueKey="requests" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Cost by provider</CardTitle>
              </CardHeader>
              <CardContent>
                <BarByGroup data={q.data.providers} labelKey="provider" valueKey="cost_usd" kind="usd" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Avg latency by provider</CardTitle>
              </CardHeader>
              <CardContent>
                <BarByGroup data={q.data.providers} labelKey="provider" valueKey="avg_latency_ms" kind="ms" />
              </CardContent>
            </Card>
          </div>

          {/* routing visualization */}
          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Routing</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2 text-sm">
                <span className="rounded bg-bg-subtle px-2 py-1 text-text-muted">Client</span>
                <span className="text-text-faint">→</span>
                <span className="rounded bg-bg-subtle px-2 py-1 text-text-muted">Router</span>
                {q.data.routing.fallback_chain.map((name, i) => {
                  const h = healthByName[name];
                  return (
                    <span key={name} className="flex items-center gap-1.5">
                      <span className="text-text-faint">{i === 0 ? "→" : "⇢"}</span>
                      <span className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-1">
                        <StatusDot status={h?.status ?? "unknown"} />
                        {providerLabel(name)}
                        {i === 0 && <span className="text-[10px] text-accent">primary</span>}
                      </span>
                    </span>
                  );
                })}
              </div>
              <div className="mt-3 text-xs text-text-muted">
                Fallback {q.data.routing.fallback_enabled ? "enabled" : "disabled"} · up to{" "}
                {q.data.routing.retry_max_attempts} attempts / provider · attempt timeout{" "}
                {q.data.routing.provider_attempt_timeout_seconds}s
              </div>
            </CardContent>
          </Card>

          {/* provider cards */}
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {q.data.providers.map((p) => {
              const h = healthByName[p.provider];
              return (
                <Card key={p.provider}>
                  <CardHeader className="flex-row items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <StatusDot status={h?.status ?? (p.enabled ? "unknown" : "disabled")} />
                      {providerLabel(p.provider)}
                    </CardTitle>
                    <span
                      className={cn(
                        "text-xs",
                        p.enabled ? "text-ok" : "text-text-faint",
                      )}
                    >
                      {p.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <Row label="Priority">
                      {p.is_primary ? "Primary" : p.fallback_priority ? `Fallback #${p.fallback_priority}` : "—"}
                    </Row>
                    <Row label="Requests">{fmtInt(p.requests)}</Row>
                    <Row label="Error rate">{fmtPct(p.error_rate)}</Row>
                    <Row label="Fallbacks">{fmtInt(p.fallback_count)}</Row>
                    <Row label="Avg latency">{fmtMs(p.avg_latency_ms)}</Row>
                    <Row label="Cost">{fmtUsd(p.cost_usd)}</Row>
                    <Row label="Tokens">{fmtInt(p.total_tokens)}</Row>
                    <div className="pt-1 text-xs text-text-faint">API key hidden — masked status only</div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      ) : (
        <EmptyState />
      )}

      {health.isError && (
        <div className="mt-4">
          <ErrorState error={health.error} onRetry={() => health.refetch()} />
        </div>
      )}
      {health.isLoading && <LoadingBlock className="mt-4 h-24" />}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted">{label}</span>
      <span className="tabular-nums">{children}</span>
    </div>
  );
}
