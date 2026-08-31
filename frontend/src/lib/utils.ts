import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const NUM = new Intl.NumberFormat("en-US");
const NUM1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return NUM.format(Math.round(n));
}

export function fmtCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Math.abs(n) < 1000) return NUM.format(n);
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function fmtUsd(n: number | null | undefined, opts?: { precise?: boolean }): string {
  if (n == null) return "—";
  if (opts?.precise || Math.abs(n) < 1) {
    return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  }
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtMs(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${NUM1.format(n / 1000)} s`;
}

export function fmtPct(rate: number | null | undefined, digits = 1): string {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(digits)}%`;
}

export function fmtChangePct(pct: number | null | undefined): string {
  if (pct == null) return "—";
  const s = pct > 0 ? "+" : "";
  return `${s}${NUM1.format(pct)}%`;
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60_000, "second"],
    [3_600_000, "minute"],
    [86_400_000, "hour"],
    [2_592_000_000, "day"],
    [31_536_000_000, "month"],
    [Infinity, "year"],
  ];
  const divisors = [1000, 60_000, 3_600_000, 86_400_000, 2_592_000_000, 31_536_000_000];
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (let i = 0; i < units.length; i++) {
    if (abs < units[i][0]) {
      return rtf.format(-Math.round(diff / divisors[i]), units[i][1]);
    }
  }
  return "—";
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];
