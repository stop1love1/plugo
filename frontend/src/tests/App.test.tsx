import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";

function renderApp(initialRoute = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  it("renders the Sites page at root route", () => {
    renderApp("/");
    expect(screen.getByText("Sites")).toBeInTheDocument();
  });

  it("renders sidebar with Plugo branding", () => {
    renderApp("/");
    expect(screen.getByText("Plugo")).toBeInTheDocument();
  });

  it("redirects unknown routes to home", () => {
    renderApp("/some/unknown/route");
    expect(screen.getByText("Sites")).toBeInTheDocument();
  });
});
