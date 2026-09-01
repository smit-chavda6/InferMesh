import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronUp, Download } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { RangePicker } from "@/components/RangePicker";
import { Button, Input } from "@/components/ui/primitives";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { CacheBadge, StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingRows } from "@/components/States";
import { RequestDrawer } from "@/components/RequestDrawer";
import { qs } from "@/api/client";
import { useRequests } from "@/api/queries";
import { useRange } from "@/hooks/useRange";
import { cn, fmtDateTime, fmtInt, fmtMs, fmtUsd, PROVIDERS, providerLabel } from "@/lib/utils";

const SORTS = ["created_at", "latency_ms", "total_tokens", "cost_usd"] as const;

export function RequestsPage() {
  const [range] = useRange();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<string>("created_at");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [openId, setOpenId] = useState<string | null>(null);

  const provider = params.get("provider") ?? undefined;
  const status = (params.get("status") as "success" | "error" | null) ?? undefined;
  const fallbackOnly = params.get("fallback_only") === "1";
  const cacheHitOnly = params.get("cache_hit_only") === "1";
  // Search lives in the URL like every other filter — shareable, survives reload,
  // and the ⌘K request-ID jump lands here. `searchInput` is just the typing buffer.
  const search = params.get("search") ?? "";
  const [searchInput, setSearchInput] = useState(search);

  useEffect(() => {
    const t = setTimeout(() => {
      const next = searchInput.trim();
      const p = new URLSearchParams(params);
      if (next === (p.get("search") ?? "")) return;
      if (next) p.set("search", next);
      else p.delete("search");
      setParams(p, { replace: true });
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput, params, setParams]);

  // Snap back to page 1 whenever the query that feeds the table changes.
  // Done during render (React's "adjust state on prop change" pattern) rather
  // than in an effect so the fetch never fires once against a stale page.
  const filterKey = JSON.stringify([
    range,
    provider,
    status,
    fallbackOnly,
    cacheHitOnly,
    search,
    sort,
    direction,
  ]);
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setPage(1);
  }

  const q = useRequests({
    range,
    page,
    page_size: 50,
    sort,
    direction,
    provider,
    status,
    fallback_only: fallbackOnly || undefined,
    cache_hit_only: cacheHitOnly || undefined,
    search: search || undefined,
  });

  const toggleParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (next.get(key) === value) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const clickSort = (col: string) => {
    if (sort === col) setDirection((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSort(col);
      setDirection("desc");
    }
  };

  const totalPages = useMemo(
    () => (q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1),
    [q.data],
  );

  const hasFilters = !!(provider || status || fallbackOnly || cacheHitOnly || search);

  const exportUrl =
    "/v1/requests/export.csv" +
    qs({
      range,
      sort,
      direction,
      provider,
      status,
      fallback_only: fallbackOnly || undefined,
      cache_hit_only: cacheHitOnly || undefined,
      search: search || undefined,
    });

  return (
    <div>
      <PageHeader
        title="Requests"
        description="Every request through the gateway, server-side paginated and filtered."
        actions={<RangePicker />}
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input
          className="h-8 w-56"
          placeholder="Search request ID / model / error…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        {PROVIDERS.map((p) => (
          <Button
            key={p.id}
            size="sm"
            variant={provider === p.id ? "default" : "outline"}
            className="h-8"
            onClick={() => toggleParam("provider", p.id)}
          >
            {p.label}
          </Button>
        ))}
        <Button
          size="sm"
          variant={status === "error" ? "default" : "outline"}
          className="h-8"
          onClick={() => toggleParam("status", "error")}
        >
          Errors only
        </Button>
        <Button
          size="sm"
          variant={fallbackOnly ? "default" : "outline"}
          className="h-8"
          onClick={() => toggleParam("fallback_only", "1")}
        >
          Fallback
        </Button>
        <Button
          size="sm"
          variant={cacheHitOnly ? "default" : "outline"}
          className="h-8"
          onClick={() => toggleParam("cache_hit_only", "1")}
        >
          Cache hits
        </Button>
        {hasFilters && (
          <Button
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() => {
              setSearchInput("");
              setParams(new URLSearchParams(range ? { range } : {}), { replace: true });
            }}
          >
            Reset
          </Button>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-text-muted">
            {q.data ? `${fmtInt(q.data.total)} results` : ""}
          </span>
          <Button asChild size="sm" variant="outline" className="h-8" title="Export the filtered rows as CSV">
            <a href={exportUrl} download>
              <Download className="size-3.5" /> CSV
            </a>
          </Button>
        </div>
      </div>

      {q.isLoading ? (
        <LoadingRows rows={12} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data?.items.length ? (
        <EmptyState
          title="No requests found"
          hint="Try changing your filters or date range."
          action={
            hasFilters ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setParams(new URLSearchParams({ range }), { replace: true })}
              >
                Reset filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Request</TH>
                <SortableTH label="Time" col="created_at" sort={sort} dir={direction} onClick={clickSort} />
                <TH>Provider / Model</TH>
                <SortableTH label="Tokens" col="total_tokens" sort={sort} dir={direction} onClick={clickSort} className="text-right" />
                <SortableTH label="Latency" col="latency_ms" sort={sort} dir={direction} onClick={clickSort} className="text-right" />
                <SortableTH label="Cost" col="cost_usd" sort={sort} dir={direction} onClick={clickSort} className="text-right" />
                <TH>Status</TH>
                <TH>Cache</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.items.map((r) => (
                <TR
                  key={r.request_id}
                  className="cursor-pointer hover:bg-bg-subtle"
                  onClick={() => setOpenId(r.request_id)}
                >
                  <TD className="font-mono text-xs text-text-muted">{r.request_id.slice(0, 16)}…</TD>
                  <TD className="text-text-muted">{fmtDateTime(r.created_at)}</TD>
                  <TD>
                    <span>{providerLabel(r.provider)}</span>
                    <span className="text-text-faint"> · {r.model}</span>
                    {r.fallback_used && <span className="ml-1 text-warn">↪</span>}
                    {r.streamed && <span className="ml-1 text-text-faint">≈</span>}
                  </TD>
                  <TD className="text-right tabular-nums">{fmtInt(r.total_tokens)}</TD>
                  <TD className="text-right tabular-nums">{fmtMs(r.latency_ms)}</TD>
                  <TD className="text-right tabular-nums">{fmtUsd(r.cost_usd, { precise: true })}</TD>
                  <TD><StatusBadge status={r.status} /></TD>
                  <TD><CacheBadge status={r.cache_status} /></TD>
                </TR>
              ))}
            </TBody>
          </Table>

          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-text-muted">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!q.data.has_more}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <RequestDrawer id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function SortableTH({
  label,
  col,
  sort,
  dir,
  onClick,
  className,
}: {
  label: string;
  col: (typeof SORTS)[number];
  sort: string;
  dir: "asc" | "desc";
  onClick: (c: string) => void;
  className?: string;
}) {
  const active = sort === col;
  return (
    <TH className={cn("cursor-pointer select-none hover:text-text", className)} onClick={() => onClick(col)}>
      <span className="inline-flex items-center gap-1">
        {label}
        {active &&
          (dir === "asc" ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />)}
      </span>
    </TH>
  );
}
