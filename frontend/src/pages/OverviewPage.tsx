import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { RangePicker } from "@/components/RangePicker";
import { KpiCard } from "@/components/KpiCard";
import { RequestVolumeChart } from "@/components/charts";
import { StatusDot } from "@/components/StatusDot";
import { EmptyState, ErrorState, LoadingBlock, LoadingCards } from "@/components/States";
import { useProviderHealth, useUsageSummary, useUsageTimeseries } from "@/api/queries";
import { useRange } from "@/hooks/useRange";
import { fmtCompact, fmtInt, fmtMs, fmtPct, fmtUsd, providerLabel } from "@/lib/utils";

export function OverviewPage() {
  const [range] = useRange();
  const summary = useUsageSummary(range);
  const series = useUsageTimeseries(range);
  const health = useProviderHealth();

  return (
    <div>
      <PageHeader
        title="System Overview"
        description="Live gateway traffic, cost, latency and provider health."
        actions={<RangePicker />}
      />

      {/* KPI cards */}
      {summary.isLoading ? (
        <LoadingCards count={4} />
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : (
        summary.data && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Total requests"
              value={fmtInt(summary.data.total_requests)}
              changePct={summary.data.total_requests_change_pct}
              sub={`${fmtInt(summary.data.success_count)} ok · ${fmtInt(summary.data.error_count)} failed`}
              sparkline={summary.data.sparkline}
            />
            <KpiCard
              label="Total cost"
              value={fmtUsd(summary.data.total_cost_usd)}
              changePct={summary.data.total_cost_change_pct}
              invertChange
              sub={`${fmtUsd(summary.data.cost_saved_usd)} saved by cache`}
            />
            <KpiCard
              label="Success rate"
              value={fmtPct(summary.data.success_rate)}
              sub={`${fmtInt(summary.data.success_count)} / ${fmtInt(summary.data.total_requests)}`}
            />
            <KpiCard
              label="Latency (p95)"
              value={fmtMs(summary.data.latency_ms.p95)}
              sub={`p50 ${fmtMs(summary.data.latency_ms.p50)} · mean ${fmtMs(summary.data.latency_ms.mean)}`}
            />
            <KpiCard
              label="Fallback rate"
              value={fmtPct(summary.data.fallback_rate)}
              sub={`${fmtInt(summary.data.fallback_count)} requests fell back`}
            />
            <KpiCard
              label="Cache hit rate"
              value={fmtPct(summary.data.cache_hit_rate)}
              sub={`${fmtInt(summary.data.cache_hit_count)} hits · ${fmtInt(summary.data.cache_miss_count)} misses`}
            />
            <KpiCard
              label="Input tokens"
              value={fmtCompact(summary.data.input_tokens)}
            />
            <KpiCard
              label="Output tokens"
              value={fmtCompact(summary.data.output_tokens)}
            />
          </div>
        )
      )}

      {/* Request volume */}
      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Request volume</CardTitle>
        </CardHeader>
        <CardContent>
          {series.isLoading ? (
            <LoadingBlock />
          ) : series.isError ? (
            <ErrorState error={series.error} onRetry={() => series.refetch()} />
          ) : !series.data?.series.length ? (
            <EmptyState title="No requests in this range" hint="Try a wider time range." />
          ) : (
            <RequestVolumeChart data={series.data.series} />
          )}
        </CardContent>
      </Card>

      {/* Provider health */}
      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Provider health</CardTitle>
        </CardHeader>
        <CardContent>
          {health.isLoading ? (
            <LoadingBlock className="h-40" />
          ) : health.isError ? (
            <ErrorState error={health.error} onRetry={() => health.refetch()} />
          ) : !health.data?.providers.length ? (
            <EmptyState
              title="No provider activity in the last 5 minutes"
              hint="Health is computed from a trailing 5-minute window of real requests."
            />
          ) : (
            <div className="divide-y divide-border">
              {health.data.providers.map((p) => (
                <div key={p.provider} className="flex items-center gap-4 py-2.5 text-sm">
                  <div className="flex w-40 items-center gap-2 font-medium">
                    <StatusDot status={p.status} />
                    {providerLabel(p.provider)}
                  </div>
                  <div className="w-24 capitalize text-text-muted">{p.status}</div>
                  <div className="w-24 tabular-nums">{fmtPct(p.success_rate)}</div>
                  <div className="w-24 tabular-nums">{fmtMs(p.avg_latency_ms)}</div>
                  <div className="ml-auto text-xs text-text-faint">
                    {fmtInt(p.request_volume)} req · {fmtPct(p.error_rate)} err
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
