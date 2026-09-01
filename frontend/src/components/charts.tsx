import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, fmtCompact, fmtDateTime, fmtMs, fmtUsd } from "@/lib/utils";

/** Row shape for the generic chart wrappers — Recharts reads fields by string key. */
type ChartRow = object;

const axis = {
  stroke: "var(--text-faint)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

function TooltipBox({
  active,
  payload,
  label,
  labelFmt,
  valueFmt,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string; dataKey?: string }[];
  label?: string | number;
  labelFmt?: (v: string | number) => string;
  valueFmt?: (v: number, key?: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs shadow-lg">
      {label != null && (
        <div className="mb-1 font-medium text-text">{labelFmt ? labelFmt(label) : String(label)}</div>
      )}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 py-0.5">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span className="text-text-muted capitalize">{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">
            {valueFmt ? valueFmt(Number(p.value), p.dataKey) : fmtCompact(Number(p.value))}
          </span>
        </div>
      ))}
    </div>
  );
}

export function MiniSparkline({ data }: { data: number[] }) {
  const rows = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={40}>
      <AreaChart data={rows} margin={{ top: 2, bottom: 0, left: 0, right: 0 }}>
        <defs>
          <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke="var(--chart-1)"
          strokeWidth={1.5}
          fill="url(#spark)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export interface VolumePoint {
  ts: string;
  success: number;
  error: number;
  fallback: number;
}
export function RequestVolumeChart({ data, height = 280 }: { data: VolumePoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 6, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="ts"
          {...axis}
          minTickGap={40}
          tickFormatter={(v) => new Date(v).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit" })}
        />
        <YAxis {...axis} width={44} tickFormatter={(v) => fmtCompact(v)} />
        <Tooltip content={<TooltipBox labelFmt={(v) => fmtDateTime(String(v))} />} />
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(v) => <span className="text-text-muted capitalize">{v}</span>}
        />
        <Area type="monotone" dataKey="success" stackId="1" stroke="var(--chart-2)" fill="var(--chart-2)" fillOpacity={0.18} strokeWidth={1.5} />
        <Area type="monotone" dataKey="error" stackId="1" stroke="var(--chart-3)" fill="var(--chart-3)" fillOpacity={0.18} strokeWidth={1.5} />
        <Area type="monotone" dataKey="fallback" stroke="var(--chart-4)" fill="var(--chart-4)" fillOpacity={0.12} strokeWidth={1.5} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function TrendLine({
  data,
  dataKey,
  kind = "number",
  valueFmt,
  height = 240,
}: {
  data: readonly ChartRow[];
  dataKey: string;
  kind?: "number" | "usd" | "ms";
  /** overrides `kind` — e.g. currency-converted money */
  valueFmt?: (v: number) => string;
  height?: number;
}) {
  const vfmt =
    valueFmt ??
    ((v: number) => (kind === "usd" ? fmtUsd(v, { precise: true }) : kind === "ms" ? fmtMs(v) : fmtCompact(v)));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: -6, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="ts"
          {...axis}
          minTickGap={40}
          tickFormatter={(v) => new Date(v).toLocaleString("en-US", { month: "short", day: "numeric" })}
        />
        <YAxis {...axis} width={54} tickFormatter={vfmt} />
        <Tooltip content={<TooltipBox labelFmt={(v) => fmtDateTime(String(v))} valueFmt={vfmt} />} />
        <Line type="monotone" dataKey={dataKey} stroke="var(--chart-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarByGroup({
  data,
  labelKey,
  valueKey,
  kind = "number",
  height = 220,
}: {
  data: readonly ChartRow[];
  labelKey: string;
  valueKey: string;
  kind?: "number" | "usd" | "ms" | "pct";
  height?: number;
}) {
  const vfmt = (v: number) =>
    kind === "usd" ? fmtUsd(v) : kind === "ms" ? fmtMs(v) : kind === "pct" ? `${(v * 100).toFixed(1)}%` : fmtCompact(v);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: -6, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey={labelKey} {...axis} />
        <YAxis {...axis} width={54} tickFormatter={vfmt} />
        <Tooltip cursor={{ fill: "var(--bg-subtle)" }} content={<TooltipBox valueFmt={vfmt} />} />
        <Bar dataKey={valueKey} radius={[4, 4, 0, 0]} maxBarSize={56}>
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DonutByGroup({
  data,
  labelKey,
  valueKey,
  height = 220,
}: {
  data: readonly ChartRow[];
  labelKey: string;
  valueKey: string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Tooltip content={<TooltipBox />} />
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={labelKey}
          innerRadius="58%"
          outerRadius="85%"
          paddingAngle={2}
          isAnimationActive={false}
        >
          {data.map((_, i) => (
            <Cell key={i} stroke="var(--panel)" strokeWidth={2} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 11 }}
          formatter={(v) => <span className="text-text-muted capitalize">{v}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
