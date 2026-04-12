import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import { useStore } from "../lib/store";

// Mock the API calls so ProtectedRoute and pages don't make real requests
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    getMe: vi.fn().mockResolvedValue({ username: "plugo", role: "admin" }),
    getSites: vi.fn().mockResolvedValue([]),
  };
});

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
  beforeEach(() => {
    useStore.setState({
      user: { username: "plugo", role: "admin", token: "test-token" },
    });
  });

  it("renders the main layout at root route", async () => {
    renderApp("/");
    await waitFor(() => {
      // The sidebar should be rendered with global navigation
      expect(screen.getByAltText("Plugo")).toBeInTheDocument();
    });
  });

  it("renders sidebar with Plugo branding", async () => {
    renderApp("/");
    await waitFor(() => {
      expect(screen.getByAltText("Plugo")).toBeInTheDocument();
    });
  });

  it("redirects unknown routes to home", async () => {
    renderApp("/some/unknown/route");
    await waitFor(() => {
      expect(screen.getByAltText("Plugo")).toBeInTheDocument();
    });
  });
});
