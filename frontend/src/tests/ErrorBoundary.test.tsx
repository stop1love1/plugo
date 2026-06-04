import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ErrorBoundary from "../components/ErrorBoundary";

function Boom(): JSX.Element {
  throw new Error("kaboom");
}

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <div>healthy content</div>
        </ErrorBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText("healthy content")).toBeInTheDocument();
  });

  it("shows a recoverable fallback when a child throws", () => {
    // Silence the expected React error log for this render.
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      </MemoryRouter>,
    );
    // Fallback shows the localized error title and a retry button.
    expect(screen.getByRole("button")).toBeInTheDocument();
    expect(screen.queryByText("healthy content")).not.toBeInTheDocument();
    spy.mockRestore();
  });
});
