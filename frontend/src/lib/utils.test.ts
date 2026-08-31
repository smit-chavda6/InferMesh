import { describe, expect, it } from "vitest";
import {
  cn,
  fmtChangePct,
  fmtCompact,
  fmtInt,
  fmtMs,
  fmtPct,
  fmtUsd,
  PROVIDERS,
  providerLabel,
} from "./utils";

describe("cn", () => {
  it("merges and dedupes tailwind classes", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    const active = false;
    expect(cn("text-sm", active && "hidden", "font-bold")).toBe("text-sm font-bold");
  });
});

describe("number formatters", () => {
  it("fmtInt rounds and groups", () => {
    expect(fmtInt(1234.6)).toBe("1,235");
    expect(fmtInt(null)).toBe("—");
  });

  it("fmtCompact abbreviates large numbers", () => {
    expect(fmtCompact(999)).toBe("999");
    expect(fmtCompact(1500)).toBe("1.5K");
    expect(fmtCompact(2_400_000)).toBe("2.4M");
    expect(fmtCompact(undefined)).toBe("—");
  });

  it("fmtUsd switches precision by magnitude", () => {
    expect(fmtUsd(12.5)).toBe("$12.50");
    expect(fmtUsd(0.0004)).toMatch(/^\$0\.0004/);
    expect(fmtUsd(1.23, { precise: true })).toBe("$1.23");
    expect(fmtUsd(null)).toBe("—");
  });

  it("fmtMs crosses into seconds at 1000", () => {
    expect(fmtMs(850)).toBe("850 ms");
    expect(fmtMs(1500)).toBe("1.5 s");
    expect(fmtMs(null)).toBe("—");
  });

  it("fmtPct multiplies a rate", () => {
    expect(fmtPct(0.955)).toBe("95.5%");
    expect(fmtPct(0.2, 0)).toBe("20%");
    expect(fmtPct(null)).toBe("—");
  });

  it("fmtChangePct signs the delta", () => {
    expect(fmtChangePct(4.2)).toBe("+4.2%");
    expect(fmtChangePct(-1.1)).toBe("-1.1%");
    expect(fmtChangePct(null)).toBe("—");
  });
});

describe("providerLabel", () => {
  it("maps every canonical provider to a display name", () => {
    expect(PROVIDERS.map((p) => p.id)).toEqual([
      "openai",
      "anthropic",
      "gemini",
      "azure_foundry",
    ]);
    expect(providerLabel("azure_foundry")).toBe("Azure AI Foundry");
    expect(providerLabel("openai")).toBe("OpenAI");
  });

  it("prettifies an unknown id instead of showing a raw slug", () => {
    expect(providerLabel("some_new_provider")).toBe("Some New Provider");
    expect(providerLabel(null)).toBe("—");
  });
});
