import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Logo } from "./Logo";

describe("Logo", () => {
  it("renders a decorative svg that inherits currentColor and takes a className", () => {
    const { container } = render(<Logo className="size-5" />);
    const svg = container.querySelector("svg")!;
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveClass("size-5");
    // no hard-coded colours — it paints with currentColor
    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{3,6}/i);
    expect(container.innerHTML).toContain("currentColor");
  });
});
