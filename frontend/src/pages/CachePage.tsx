import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/PageHeader";
import { KpiCard } from "@/components/KpiCard";
import { EmptyState, ErrorState, LoadingCards } from "@/components/States";
import { useCacheStats } from "@/api/queries";
import { fmtDateTime, fmtInt, fmtMs, fmtPct, fmtUsd } from "@/lib/utils";

export function CachePage() {
  const q = useCacheStats();

  return (
    <div>
      <PageHeader
        title="Cache Analytics"
        description="Exact-match cache in Redis; optional semantic layer in pgvector. Entries are identified by hash — never raw prompts."
      />

      {q.isLoading ? (
        <LoadingCards count={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Hit rate" value={fmtPct(q.data.hit_rate)} sub={`${fmtInt(q.data.hits)} hits · ${fmtInt(q.data.misses)} misses`} />
            <KpiCard label="Cost saved (est.)" value={fmtUsd(q.data.cost_saved_usd)} sub="sum of would-be cost on hits" />
            <KpiCard label="Latency saved (est.)" value={fmtMs(q.data.latency_saved_ms_est)} sub="hits × avg miss latency" />
            <KpiCard
              label="Entries"
              value={fmtInt((q.data.exact_entries ?? 0) + q.data.semantic_entries)}
              sub={`${fmtInt(q.data.exact_entries)} exact · ${fmtInt(q.data.semantic_entries)} semantic`}
            />
          </div>

          {!q.data.semantic_enabled && (
            <div className="mt-4 rounded-md border border-border bg-bg-subtle px-3 py-2 text-xs text-text-muted">
              Semantic caching is <strong>disabled</strong> — no embedding key/deployment is configured.
              The gateway is running exact-match only.
            </div>
          )}

          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Recent semantic entries</CardTitle>
            </CardHeader>
            <CardContent>
              {!q.data.recent_entries.length ? (
                <EmptyState title="No semantic cache entries" hint="Populated once an embedding key is configured and requests flow." />
              ) : (
                <Table>
                  <THead>
                    <TR>
                      <TH>Cache key (hash)</TH>
                      <TH>Model</TH>
                      <TH>Created</TH>
                      <TH>Expires</TH>
                      <TH className="text-right">Hits</TH>
                      <TH className="text-right">Est. savings</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {q.data.recent_entries.map((e) => (
                      <TR key={e.cache_key}>
                        <TD className="font-mono text-xs text-text-muted">{e.cache_key.slice(0, 20)}…</TD>
                        <TD>{e.model}</TD>
                        <TD className="text-text-muted">{fmtDateTime(e.created_at)}</TD>
                        <TD className="text-text-muted">{fmtDateTime(e.expires_at)}</TD>
                        <TD className="text-right tabular-nums">{fmtInt(e.hits)}</TD>
                        <TD className="text-right tabular-nums">{fmtUsd(e.estimated_savings_usd, { precise: true })}</TD>
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
