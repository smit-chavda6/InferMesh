import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  SegmentedControl,
} from "@/components/ui/primitives";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/PageHeader";
import { RangePicker } from "@/components/RangePicker";
import { KpiCard } from "@/components/KpiCard";
import { TrendLine } from "@/components/charts";
import { EmptyState, ErrorState, LoadingBlock, LoadingCards } from "@/components/States";
import { useCostBreakdown, useFx, useUsageSummary, useUsageTimeseries } from "@/api/queries";
import { useRange } from "@/hooks/useRange";
import type { TimeseriesPoint } from "@/api/types";
import { fmtInt, fmtMoney, fmtMoneyAxis, type Currency } from "@/lib/utils";

const RANGE_DAYS: Record<string, number> = { "1h": 1 / 24, "24h": 1, "7d": 7, "30d": 30 };
const CURRENCY_KEY = "gw-currency";
const INR_FALLBACK = 87.5; // used only until GET /v1/fx resolves

function storedCurrency(): Currency {
  try {
    return localStorage.getItem(CURRENCY_KEY) === "INR" ? "INR" : "USD";
  } catch {
    return "USD";
  }
}

/** Drop trailing buckets with zero requests — the newest bucket is usually
 *  still in progress, which otherwise reads as the line crashing to $0. A
 *  genuinely quiet stretch *followed by* more traffic is left alone. */
function dropTrailingIdleBuckets(series: TimeseriesPoint[]): TimeseriesPoint[] {
  let end = series.length;
  while (end > 0 && series[end - 1].total === 0) end--;
  return series.slice(0, end);
}

/** X-axis tick formatter matched to the series' bucket width: sub-daily
 *  buckets ("1 minute" / "1 hour") need a time-of-day, not just the date. */
function xAxisFmt(bucket: string | undefined) {
  const opts: Intl.DateTimeFormatOptions =
    bucket === "1 day"
      ? { month: "short", day: "numeric" }
      : { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false };
  return (v: string | number) => new Date(v).toLocaleString("en-US", opts);
}

export function CostsPage() {
  const [range] = useRange();
  const [groupBy, setGroupBy] = useState<"model" | "provider" | "project">("model");
  const [currency, setCurrency] = useState<Currency>(storedCurrency);
  const summary = useUsageSummary(range);
  const series = useUsageTimeseries(range);
  const breakdown = useCostBreakdown(range, groupBy);
  const fx = useFx();

  const rate = currency === "INR" ? (fx.data?.rates.INR ?? INR_FALLBACK) : 1;
  const money = (n: number | null | undefined, opts?: { precise?: boolean }) =>
    fmtMoney(n == null ? n : n * rate, currency, opts);
  const chartSeries = series.data ? dropTrailingIdleBuckets(series.data.series) : [];

  const pickCurrency = (c: Currency) => {
    setCurrency(c);
    try {
      localStorage.setItem(CURRENCY_KEY, c);
    } catch {
      /* private mode */
    }
  };

  const days = RANGE_DAYS[range] ?? 1;
  const dailyAvg = summary.data ? summary.data.total_cost_usd / days : 0;

  return (
    <div>
      <PageHeader
        title="Cost Analytics"
        description="Where the spend goes — by model, provider and project."
        actions={
          <div className="flex items-center gap-2">
            <SegmentedControl
              aria-label="Display currency"
              value={currency}
              onValueChange={pickCurrency}
              options={[
                { value: "USD", label: "USD" },
                { value: "INR", label: "INR" },
              ]}
            />
            <RangePicker />
          </div>
        }
      />

      {summary.isLoading ? (
        <LoadingCards count={3} />
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : summary.data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <KpiCard
              label="Total cost"
              value={money(summary.data.total_cost_usd)}
              changePct={summary.data.total_cost_change_pct}
              invertChange
            />
            <KpiCard
              label="Daily average"
              value={money(dailyAvg)}
              sub={`over ${days < 1 ? "the hour" : days + " days"}`}
            />
            <KpiCard
              label="Projected monthly"
              value={money(dailyAvg * 30)}
              sub="daily average × 30 — estimate"
            />
          </div>
          {currency === "INR" && (
            <p className="mt-2 text-xs text-text-faint">
              Converted at 1&nbsp;USD&nbsp;≈&nbsp;₹{rate.toFixed(2)}
              {fx.data?.source === "frankfurter" && fx.data.as_of
                ? ` · ECB reference, ${fx.data.as_of}`
                : " · estimate"}
              . Costs are billed in USD.
            </p>
          )}
        </>
      ) : null}

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Cost over time</CardTitle>
        </CardHeader>
        <CardContent>
          {series.isLoading ? (
            <LoadingBlock />
          ) : series.isError ? (
            <ErrorState error={series.error} onRetry={() => series.refetch()} />
          ) : !chartSeries.length ? (
            <EmptyState title="No cost data in this range" />
          ) : (
            <TrendLine
              data={chartSeries}
              dataKey="cost_usd"
              valueFmt={(v) => money(v, { precise: true })}
              axisValueFmt={(v) => fmtMoneyAxis(v * rate, currency)}
              xFmt={xAxisFmt(series.data?.range.bucket)}
            />
          )}
        </CardContent>
      </Card>

      <Card className="mt-5">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Breakdown</CardTitle>
          <SegmentedControl
            aria-label="Break cost down by"
            value={groupBy}
            onValueChange={setGroupBy}
            options={[
              { value: "model", label: "By model" },
              { value: "provider", label: "By provider" },
              { value: "project", label: "By project" },
            ]}
          />
        </CardHeader>
        <CardContent>
          {breakdown.isLoading ? (
            <LoadingBlock className="h-56" />
          ) : breakdown.isError ? (
            <ErrorState error={breakdown.error} onRetry={() => breakdown.refetch()} />
          ) : !breakdown.data?.rows.length ? (
            <EmptyState title="No spend to break down" />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>
                    {groupBy === "model"
                      ? "Provider / Model"
                      : groupBy === "provider"
                        ? "Provider"
                        : "Project"}
                  </TH>
                  <TH className="text-right">Input tok</TH>
                  <TH className="text-right">Output tok</TH>
                  <TH className="text-right">Requests</TH>
                  <TH className="text-right">Cost</TH>
                  <TH className="text-right">Avg / req</TH>
                </TR>
              </THead>
              <TBody>
                {breakdown.data.rows.map((r, i) => (
                  <TR key={i}>
                    <TD className="capitalize">
                      {groupBy === "model"
                        ? `${r.provider} · ${r.model}`
                        : (r.provider ?? r.project)}
                    </TD>
                    <TD className="text-right tabular-nums">{fmtInt(r.input_tokens)}</TD>
                    <TD className="text-right tabular-nums">{fmtInt(r.output_tokens)}</TD>
                    <TD className="text-right tabular-nums">{fmtInt(r.requests)}</TD>
                    <TD className="text-right tabular-nums">{money(r.cost_usd)}</TD>
                    <TD className="text-right tabular-nums">
                      {money(r.avg_cost_per_request, { precise: true })}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
