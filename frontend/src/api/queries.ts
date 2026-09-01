import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, qs } from "./client";
import type {
  AdminInfo,
  AlertsResponse,
  CacheStats,
  CostBreakdownResponse,
  CreatedProject,
  FxResponse,
  ProjectRow,
  ProvidersResponse,
  ProviderHealthRow,
  RangeKey,
  RateLimitsResponse,
  RequestsPage,
  StoredRequest,
  SystemHealth,
  TimeseriesResponse,
  UsageSummary,
} from "./types";

const R = (range: RangeKey) => `range=${range}`;

/* ---------------- auth ---------------- */
export function useAuthMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<AdminInfo>("/v1/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      apiFetch<AdminInfo>("/v1/auth/login", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.setQueryData(["auth", "me"], data);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: boolean }>("/v1/auth/logout", { method: "POST" }),
    onSuccess: () => {
      qc.clear();
      // Full reload to the root: the app re-boots into the logged-out state
      // (App → useAuthMe 401 → LoginPage) and no dashboard data lingers in
      // memory. A bare qc.clear() leaves the mounted useAuthMe observer holding
      // its stale user object, so the gate never flips to the login screen.
      window.location.assign("/");
    },
  });
}

/* ---------------- dashboard reads ---------------- */
export function useUsageSummary(range: RangeKey) {
  return useQuery({
    queryKey: ["usage", "summary", range],
    queryFn: () => apiFetch<UsageSummary>(`/v1/usage/summary?${R(range)}`),
  });
}

export function useUsageTimeseries(range: RangeKey) {
  return useQuery({
    queryKey: ["usage", "timeseries", range],
    queryFn: () => apiFetch<TimeseriesResponse>(`/v1/usage/timeseries?${R(range)}`),
  });
}

export interface RequestsQuery {
  range: RangeKey;
  page: number;
  page_size: number;
  sort?: string;
  direction?: "asc" | "desc";
  provider?: string;
  model?: string;
  status?: "success" | "error";
  project_id?: string;
  fallback_only?: boolean;
  cache_hit_only?: boolean;
  search?: string;
}
export function useRequests(q: RequestsQuery) {
  return useQuery({
    queryKey: ["requests", q],
    queryFn: () => apiFetch<RequestsPage>(`/v1/requests${qs({ ...q })}`),
    placeholderData: (prev) => prev,
  });
}

/** Recent requests for the Live Activity feed — polls while `live` is true. */
export function useLiveRequests(live: boolean) {
  return useQuery({
    queryKey: ["requests", "live"],
    queryFn: () =>
      apiFetch<RequestsPage>(
        "/v1/requests?range=1h&page=1&page_size=30&sort=created_at&direction=desc",
      ),
    refetchInterval: live ? 4000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useRequestDetail(id: string | null) {
  return useQuery({
    queryKey: ["requests", "detail", id],
    queryFn: () => apiFetch<StoredRequest>(`/v1/requests/${id}`),
    enabled: !!id,
  });
}

export function useCostBreakdown(range: RangeKey, groupBy: "model" | "provider" | "project") {
  return useQuery({
    queryKey: ["usage", "cost-breakdown", range, groupBy],
    queryFn: () =>
      apiFetch<CostBreakdownResponse>(`/v1/usage/cost-breakdown?${R(range)}&group_by=${groupBy}`),
  });
}

/** USD reference rates for the display-only currency switch (refetched rarely). */
export function useFx() {
  return useQuery({
    queryKey: ["fx"],
    queryFn: () => apiFetch<FxResponse>("/v1/fx"),
    staleTime: 6 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  });
}

export function useProviders(range: RangeKey) {
  return useQuery({
    queryKey: ["providers", range],
    queryFn: () => apiFetch<ProvidersResponse>(`/v1/providers?${R(range)}`),
  });
}

export function useProviderHealth() {
  return useQuery({
    queryKey: ["providers", "health"],
    queryFn: () => apiFetch<{ providers: ProviderHealthRow[] }>("/v1/providers/health"),
    refetchInterval: 15_000,
  });
}

export function useCacheStats() {
  return useQuery({
    queryKey: ["cache", "stats"],
    queryFn: () => apiFetch<CacheStats>("/v1/cache/stats"),
  });
}

export function useRateLimits() {
  return useQuery({
    queryKey: ["rate-limits"],
    queryFn: () => apiFetch<RateLimitsResponse>("/v1/rate-limits"),
    refetchInterval: 10_000,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => apiFetch<{ projects: ProjectRow[] }>("/v1/projects"),
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => apiFetch<AlertsResponse>("/v1/alerts"),
    refetchInterval: 20_000,
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: () => apiFetch<SystemHealth>("/v1/system/health"),
    refetchInterval: 15_000,
  });
}

/* ---------------- project mutations ---------------- */
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; rate_limit_per_minute: number }) =>
      apiFetch<CreatedProject>("/v1/projects", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useRotateKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<CreatedProject>(`/v1/projects/${id}/rotate`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useRevokeProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<ProjectRow>(`/v1/projects/${id}/revoke`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["rate-limits"] });
    },
  });
}
