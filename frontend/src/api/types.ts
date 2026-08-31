/** TS mirrors of the backend's dashboard-ready response shapes (§27). */

export type RangeKey = "1h" | "24h" | "7d" | "30d";
export type ProviderName = "openai" | "anthropic" | "gemini" | "azure_foundry";
export type HealthStatus = "healthy" | "degraded" | "unhealthy" | "disabled" | "unknown";

export interface AdminInfo {
  email: string;
}

export interface UsageSummary {
  range: { key: string; start: string; end: string };
  total_requests: number;
  total_requests_prev: number;
  total_requests_change_pct: number | null;
  success_count: number;
  error_count: number;
  success_rate: number | null;
  total_cost_usd: number;
  total_cost_usd_prev: number;
  total_cost_change_pct: number | null;
  cost_saved_usd: number;
  fallback_count: number;
  fallback_rate: number | null;
  cache_hit_count: number;
  cache_miss_count: number;
  cache_hit_rate: number | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: { mean: number; p50: number; p95: number };
  sparkline: number[];
}

export interface TimeseriesPoint {
  ts: string;
  total: number;
  success: number;
  error: number;
  fallback: number;
  cost_usd: number;
  avg_latency_ms: number;
}
export interface TimeseriesResponse {
  range: { key: string; start: string; end: string; bucket: string };
  series: TimeseriesPoint[];
}

export interface RequestRow {
  request_id: string;
  created_at: string;
  provider: string;
  model: string;
  upstream_model: string | null;
  status: "success" | "error";
  http_status: number | null;
  error_type: string | null;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cache_status: "HIT" | "MISS" | "DISABLED";
  fallback_used: boolean;
  retries: number;
  project_id: string | null;
  project_name: string | null;
  api_key_prefix: string | null;
  finish_reason: string | null;
  streamed: boolean;
}
export interface RequestsPage {
  items: RequestRow[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}

export interface StoredRequest extends RequestRow {
  error_message: string | null;
  input_cost_usd: number | null;
  output_cost_usd: number | null;
  pricing_version: string | null;
  provider_chain:
    | { provider: string; model: string; outcome: string; retries: number; error?: string }[]
    | null;
  cache_key: string | null;
  message_count: number;
}

export interface CostBreakdownRow {
  provider?: string;
  model?: string;
  project?: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cost_saved_usd: number;
  avg_cost_per_request: number;
}
export interface CostBreakdownResponse {
  range: { key: string; start: string; end: string };
  group_by: "model" | "provider" | "project";
  rows: CostBreakdownRow[];
}

export interface ProviderRow {
  provider: string;
  enabled: boolean;
  is_primary: boolean;
  fallback_priority: number | null;
  requests: number;
  error_rate: number;
  fallback_count: number;
  avg_latency_ms: number;
  cost_usd: number;
  total_tokens: number;
}
export interface ProvidersResponse {
  range: { key: string; start: string; end: string };
  routing: {
    primary: string;
    fallback_chain: string[];
    fallback_enabled: boolean;
    retry_max_attempts: number;
    retry_base_delay_seconds: number;
    provider_attempt_timeout_seconds: number;
  };
  providers: ProviderRow[];
}

export interface ProviderHealthRow {
  provider: string;
  status: HealthStatus;
  success_rate: number;
  error_rate: number;
  avg_latency_ms: number;
  request_volume: number;
  consecutive_failures_3plus: boolean;
  window_minutes: number;
}

export interface CacheStats {
  hits: number;
  misses: number;
  hit_rate: number | null;
  cost_saved_usd: number;
  latency_saved_ms_est: number;
  exact_entries: number | null;
  semantic_entries: number;
  semantic_enabled: boolean;
  recent_entries: {
    cache_key: string;
    model: string;
    provider: string;
    created_at: string;
    expires_at: string | null;
    hits: number;
    estimated_savings_usd: number;
  }[];
}

export interface RateLimitsResponse {
  anon_limit_per_minute: number;
  projects: {
    project_id: string;
    project: string;
    status: string;
    limit: number;
    window_seconds: number;
    current: number;
    remaining: number;
  }[];
  recent_429: {
    request_id: string;
    created_at: string;
    project_id: string | null;
    project_name: string | null;
    api_key_prefix: string | null;
  }[];
}

export interface ProjectRow {
  id: string;
  name: string;
  key_prefix: string;
  status: string;
  rate_limit_per_minute: number;
  rate_limit_window_seconds: number;
  created_at: string;
  last_used_at: string | null;
  requests: number;
  cost_usd: number;
}
export interface CreatedProject extends ProjectRow {
  api_key: string;
}

export interface AlertRow {
  id: number;
  type: string;
  severity: "info" | "warning" | "critical";
  status: string;
  provider: string | null;
  title: string;
  message: string;
  acknowledged: boolean;
  first_seen_at: string;
  last_seen_at: string;
}
export interface AlertsResponse {
  unread_count: number;
  alerts: AlertRow[];
}

export interface SystemHealth {
  gateway: { status: string };
  dependencies: Record<
    string,
    {
      status: string;
      latency_ms?: number;
      success_rate?: number | null;
      avg_latency_ms?: number | null;
      checked_at: string;
    }
  >;
}
