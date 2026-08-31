import { useSearchParams } from "react-router-dom";
import type { RangeKey } from "@/api/types";

const RANGES: RangeKey[] = ["1h", "24h", "7d", "30d"];

export function useRange(): [RangeKey, (r: RangeKey) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("range");
  const range: RangeKey = RANGES.includes(raw as RangeKey) ? (raw as RangeKey) : "24h";
  const set = (r: RangeKey) => {
    const next = new URLSearchParams(params);
    next.set("range", r);
    setParams(next, { replace: true });
  };
  return [range, set];
}

export { RANGES };
