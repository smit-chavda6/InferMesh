import { createContext, useContext } from "react";

export type ToastTone = "ok" | "err" | "info";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
  /** ms before auto-dismiss; 0 keeps it until closed. Default 4000. */
  duration?: number;
}

export interface ToastRecord extends ToastInput {
  id: number;
}

export interface ToastApi {
  toast: (t: ToastInput) => number;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}
