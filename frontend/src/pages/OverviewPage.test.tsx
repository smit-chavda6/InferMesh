import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { OverviewPage } from "./OverviewPage";
import * as queries from "@/api/queries";
import type { UsageSummary } from "@/api/types";

vi.mock("@/api/queries");

const q = vi.mocked(queries);

// minimal shapes — the page only reads these fields
const SUMMARY: UsageSummary = {
  range: { key: "7d", start: "", end: "" },
  total_requests: 22952,
  total_requests_prev: 23631,
  total_requests_change_pct: -2.87,
  success_count: 21920,
  error_count: 1032,
  success_rate: 0.955,
  total_cost_usd: 22.97,
  total_cost_usd_prev: 23.2,
  total_cost_change_pct: -0.99,
  cost_saved_usd: 5.56,
  fallback_count: 632,
  fallback_rate: 0.0275,
  cache_hit_count: 4397,
  cache_miss_count: 17424,
  cache_hit_rate: 0.2015,
  input_tokens: 4_368_820,
  output_tokens: 3_267_198,
  latency_ms: { mean: 596.64, p50: 494.28, p95: 1328.79 },
  sparkline: [1, 2, 3, 4],
};

// The page only reads { data, isLoading, isError, error, refetch } off each hook.
// `as never` sidesteps re-declaring each hook's full UseQueryResult union.
const ok = (data: unknown) =>
  ({ data, isLoading: false, isError: false, error: null, refetch: vi.fn() }) as never;
const loading = () =>
  ({ data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() }) as never;
const failed = (error: unknown) =>
  ({ data: undefined, isLoading: false, isError: true, error, refetch: vi.fn() }) as never;

beforeEach(() => {
  vi.clearAllMocks();
  q.useUsageTimeseries.mockReturnValue(ok({ range: { key: "7d", start: "", end: "", bucket: "1 day" }, series: [] }));
  q.useProviderHealth.mockReturnValue(ok({ providers: [] }));
});

describe("OverviewPage", () => {
  it("shows skeletons while the summary is loading", () => {
    q.useUsageSummary.mockReturnValue(loading());
    const { container } = renderWithProviders(<OverviewPage />);
    expect(container.querySelectorAll(".animate-pulse, [data-slot='skeleton']").length).toBeGreaterThan(0);
    expect(screen.queryByText("22,952")).not.toBeInTheDocument();
  });

  it("renders KPI values from the summary payload", () => {
    q.useUsageSummary.mockReturnValue(ok(SUMMARY));
    renderWithProviders(<OverviewPage />);
    expect(screen.getByText("22,952")).toBeInTheDocument(); // total requests
    expect(screen.getByText("95.5%")).toBeInTheDocument(); // success rate
    expect(screen.getByText("1.3 s")).toBeInTheDocument(); // p95 latency
    expect(screen.getByText(/5\.56 saved by cache/)).toBeInTheDocument();
  });

  it("surfaces an API error with a retry affordance", () => {
    q.useUsageSummary.mockReturnValue(failed(new Error("boom")));
    renderWithProviders(<OverviewPage />);
    expect(screen.getByText("Couldn't load this data")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows the empty state for provider health when the window is quiet", () => {
    q.useUsageSummary.mockReturnValue(ok(SUMMARY));
    renderWithProviders(<OverviewPage />);
    expect(
      screen.getByText("No provider activity in the last 5 minutes"),
    ).toBeInTheDocument();
  });
});
