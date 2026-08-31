import { Sheet, SheetContent } from "@/components/ui/overlays";
import { CacheBadge, StatusBadge } from "@/components/badges";
import { ErrorState, LoadingRows } from "@/components/States";
import { useRequestDetail } from "@/api/queries";
import { fmtDateTime, fmtInt, fmtMs, fmtUsd, providerLabel } from "@/lib/utils";

const PIPELINE = [
  "Request received",
  "Validation",
  "Rate limit check",
  "Cache check",
  "Provider selected",
  "LLM request",
  "Response received",
  "Usage recorded",
];

export function RequestDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useRequestDetail(id);
  const r = q.data;

  return (
    <Sheet open={!!id} onOpenChange={(v) => !v && onClose()}>
      <SheetContent>
        <div className="border-b border-border p-5">
          <div className="text-xs text-text-faint">Request</div>
          <div className="mt-0.5 break-all font-mono text-sm">{id}</div>
        </div>

        <div className="space-y-6 p-5">
          {q.isLoading ? (
            <LoadingRows rows={6} />
          ) : q.isError ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          ) : r ? (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <Field label="Status">
                  <StatusBadge status={r.status} />{" "}
                  {r.http_status && <span className="text-text-faint">· {r.http_status}</span>}
                </Field>
                <Field label="Cache">
                  <CacheBadge status={r.cache_status} />
                </Field>
                <Field label="Provider">
                  <span>{providerLabel(r.provider)}</span>
                </Field>
                <Field label="Model">{r.model}</Field>
                <Field label="Upstream model">{r.upstream_model ?? "—"}</Field>
                <Field label="Time">{fmtDateTime(r.created_at)}</Field>
                <Field label="Latency">{fmtMs(r.latency_ms)}</Field>
                <Field label="Retries">{r.retries}</Field>
                <Field label="Input tokens">{fmtInt(r.prompt_tokens)}</Field>
                <Field label="Output tokens">{fmtInt(r.completion_tokens)}</Field>
                <Field label="Cost">{fmtUsd(r.cost_usd, { precise: true })}</Field>
                <Field label="Streamed">{r.streamed ? "yes" : "no"}</Field>
                <Field label="Project">{r.project_name ?? "anonymous"}</Field>
                <Field label="API key">{r.api_key_prefix ?? "—"}</Field>
                {r.finish_reason && <Field label="Finish reason">{r.finish_reason}</Field>}
                {r.pricing_version && <Field label="Pricing">{r.pricing_version}</Field>}
              </div>

              {r.error_message && (
                <div className="rounded-md bg-err-bg px-3 py-2 text-xs text-err">{r.error_message}</div>
              )}

              {/* fallback / retry chain */}
              {r.provider_chain && r.provider_chain.length > 0 && (
                <div>
                  <div className="mb-2 text-xs font-medium text-text-muted">Routing chain</div>
                  <div className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs">
                    <span className="rounded bg-bg-subtle px-1.5 py-1 text-text-muted">Client</span>
                    {r.provider_chain.map((a, i) => (
                      <span key={i} className="flex items-center gap-1">
                        <span className="text-text-faint">→</span>
                        <span
                          className={
                            "rounded px-1.5 py-1 " +
                            (a.outcome === "success"
                              ? "bg-ok-bg text-ok"
                              : a.outcome === "timeout"
                                ? "bg-warn-bg text-warn"
                                : "bg-err-bg text-err")
                          }
                        >
                          {providerLabel(a.provider)} · {a.outcome}
                          {a.retries ? ` (${a.retries}×)` : ""}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* pipeline timeline */}
              <div>
                <div className="mb-2 text-xs font-medium text-text-muted">Pipeline</div>
                <ol className="space-y-1.5 text-xs">
                  {PIPELINE.map((step) => (
                    <li key={step} className="flex items-center gap-2 text-text-muted">
                      <span className="size-1.5 rounded-full bg-accent/70" />
                      {step}
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-[11px] text-text-faint">
                  Prompt / completion content is never stored (see privacy notes).
                </p>
              </div>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}
