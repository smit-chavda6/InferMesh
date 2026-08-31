import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Routes, Route, useLocation } from "react-router-dom";
import { renderWithProviders } from "@/test/render";
import { RangePicker } from "./RangePicker";

function LocationProbe() {
  return <output data-testid="search">{useLocation().search}</output>;
}

describe("RangePicker", () => {
  it("defaults to 24h and reflects the ?range param", () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<RangePicker />} />
      </Routes>,
      { route: "/?range=7d" },
    );
    const sevenD = screen.getByRole("button", { name: "7d" });
    // active button carries the accent background class
    expect(sevenD.className).toMatch(/bg-accent/);
    expect(screen.getByRole("button", { name: "24h" }).className).not.toMatch(/bg-accent/);
  });

  it("writes the chosen range into the URL query string", async () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={
            <>
              <RangePicker />
              <LocationProbe />
            </>
          }
        />
      </Routes>,
      { route: "/" },
    );
    await userEvent.click(screen.getByRole("button", { name: "1h" }));
    expect(screen.getByTestId("search")).toHaveTextContent("range=1h");
  });
});
