import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Models from "../pages/Models";

vi.mock("../components/LLMKeysSection", () => ({
  LLMKeysSection: () => <div>LLM Keys Section</div>,
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("../lib/api", () => ({
  getModelsProviders: vi.fn().mockResolvedValue([
    {
      id: "openai",
      name: "OpenAI",
      models: [{ id: "gpt-4o", name: "GPT-4o", description: "Test model" }],
      requires_key: true,
      has_key: true,
      key_status: "invalid",
    },
  ]),
  getCustomModels: vi.fn().mockResolvedValue([]),
  addCustomModel: vi.fn().mockResolvedValue({ message: "ok" }),
  deleteCustomModel: vi.fn().mockResolvedValue({ message: "ok" }),
}));

function renderModels() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <Models />
    </QueryClientProvider>,
  );
}

describe("Models", () => {
  it("shows invalid key status instead of configured when provider key is broken", async () => {
    renderModels();

    expect(await screen.findByText("API Key không hợp lệ")).toBeInTheDocument();
    expect(screen.queryByText("API Key configured")).not.toBeInTheDocument();
  });

  it("keeps the custom provider input visible while typing a custom provider name", async () => {
    renderModels();

    fireEvent.click(await screen.findByRole("button", { name: "Thêm model" }));

    const providerSelect = screen.getByRole("combobox");
    fireEvent.change(providerSelect, { target: { value: "__custom__" } });

    const customProviderInput = await screen.findByPlaceholderText("my-provider");
    fireEvent.change(customProviderInput, { target: { value: "my-provider" } });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("my-provider")).toBeInTheDocument();
      expect(screen.getByDisplayValue("my-provider")).toBeInTheDocument();
    });
  });
});
