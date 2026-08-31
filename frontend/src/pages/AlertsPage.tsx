import { CheckCircle2 } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { PageHeader } from "@/components/PageHeader";
import { SeverityBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingRows } from "@/components/States";
import { useAlerts } from "@/api/queries";
import { fmtRelative } from "@/lib/utils";

export function AlertsPage() {
  const q = useAlerts();

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Evaluated from recent request data: provider health, dependency outages, error-rate and rate-limit spikes."
      />

      {q.isLoading ? (
        <LoadingRows rows={5} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data?.alerts.length ? (
        <EmptyState
          title="All clear"
          hint="No active alerts. Providers healthy, dependencies reachable."
        />
      ) : (
        <div className="space-y-2">
          {q.data.alerts.map((a) => (
            <Card key={a.id} className="flex items-start gap-3 p-3.5">
              <div className="mt-0.5">
                <SeverityBadge severity={a.severity} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.title}</span>
                  {a.provider && (
                    <span className="text-xs capitalize text-text-faint">{a.provider}</span>
                  )}
                </div>
                <p className="mt-0.5 text-sm text-text-muted">{a.message}</p>
                <div className="mt-1 text-xs text-text-faint">
                  first seen {fmtRelative(a.first_seen_at)} · updated {fmtRelative(a.last_seen_at)}
                </div>
              </div>
              {a.acknowledged && <CheckCircle2 className="size-4 text-text-faint" />}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
