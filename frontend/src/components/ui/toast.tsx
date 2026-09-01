import * as React from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ToastContext,
  type ToastInput,
  type ToastRecord,
  type ToastTone,
} from "@/hooks/useToast";

let _id = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastRecord[]>([]);
  const timers = React.useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = React.useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const toast = React.useCallback(
    (t: ToastInput) => {
      const id = ++_id;
      setToasts((list) => [...list, { ...t, id }]);
      const duration = t.duration ?? 4000;
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration),
        );
      }
      return id;
    },
    [dismiss],
  );

  React.useEffect(() => {
    const map = timers.current;
    return () => map.forEach(clearTimeout);
  }, []);

  const api = React.useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const ICON: Record<ToastTone, React.ComponentType<{ className?: string }>> = {
  ok: CheckCircle2,
  err: AlertTriangle,
  info: Info,
};
const TONE: Record<ToastTone, string> = {
  ok: "text-ok",
  err: "text-err",
  info: "text-info",
};

function Toaster({
  toasts,
  onDismiss,
}: {
  toasts: ToastRecord[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div
      role="region"
      aria-label="Notifications"
      className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-[min(92vw,22rem)] flex-col gap-2"
    >
      {toasts.map((t) => {
        const tone = t.tone ?? "info";
        const Icon = ICON[tone];
        return (
          <div
            key={t.id}
            role="status"
            aria-live="polite"
            className="animate-in pointer-events-auto flex items-start gap-2.5 rounded-lg border border-border bg-panel p-3 shadow-lg"
          >
            <Icon className={cn("mt-0.5 size-4 shrink-0", TONE[tone])} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-text">{t.title}</div>
              {t.description && (
                <div className="mt-0.5 break-words text-xs text-text-muted">{t.description}</div>
              )}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => onDismiss(t.id)}
              className="rounded p-0.5 text-text-faint transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
            >
              <X className="size-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
