import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LLMSettingsPanel } from "../src/components/LLMSettings";
import userEvent from "@testing-library/user-event";

const ollama = {
  provider: "ollama" as const,
  base_url: "http://localhost:11434",
  model: "qwen3:32b",
};
const openai = {
  provider: "openai-compatible" as const,
  base_url: "https://api.example.com/v1",
  model: "gpt-4o-mini",
};

describe("LLMSettings", () => {
  it("accepts a hosted Ollama URL and shows an optional API key", () => {
    render(
      <LLMSettingsPanel
        settings={ollama}
        apiKey=""
        onChange={vi.fn()}
        onApiKeyChange={vi.fn()}
      />
    );
    expect(screen.getByDisplayValue("http://localhost:11434")).toBeInTheDocument();
    expect(screen.getByDisplayValue("qwen3:32b")).toBeInTheDocument();

    const keyInput = screen.getByPlaceholderText(/leave empty if not needed/);
    expect(keyInput).toHaveAttribute("type", "password");
    expect(screen.getByText(/\(optional/i)).toBeInTheDocument();
  });

  it("marks the key required for OpenAI-compatible providers", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LLMSettingsPanel
        settings={ollama}
        apiKey=""
        onChange={onChange}
        onApiKeyChange={vi.fn()}
      />
    );

    await user.selectOptions(screen.getByLabelText(/Provider/), "openai-compatible");
    expect(onChange).toHaveBeenCalledWith({ provider: "openai-compatible" });

    // Re-render as the parent would after state change.
    render(
      <LLMSettingsPanel
        settings={openai}
        apiKey=""
        onChange={onChange}
        onApiKeyChange={vi.fn()}
      />
    );
    expect(screen.getByText(/\(required, kept in memory only\)/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("sk-...")).toBeInTheDocument();
  });

  it("emits base URL / model edits and API key through dedicated callbacks", async () => {
    const onChange = vi.fn();
    const onApiKeyChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LLMSettingsPanel
        settings={{ ...ollama, base_url: "", model: "" }}
        apiKey=""
        onChange={onChange}
        onApiKeyChange={onApiKeyChange}
      />
    );

    await user.type(screen.getAllByRole("textbox")[0]!, "h");
    // base_url input is the first textbox rendered before model input
    expect(onChange).toHaveBeenCalled();

    await user.type(screen.getByPlaceholderText("leave empty if not needed"), "s");
    expect(onApiKeyChange).toHaveBeenCalledWith("s");
  });

  it("never persists the API key to localStorage", () => {
    window.localStorage.setItem("jobhunter.llmModel", JSON.stringify("kept"));
    render(
      <LLMSettingsPanel
        settings={ollama}
        apiKey="super-secret"
        onChange={vi.fn()}
        onApiKeyChange={vi.fn()}
      />
    );
    for (let i = 0; i < window.localStorage.length; i++) {
      const value = window.localStorage.getItem(window.localStorage.key(i)!) ?? "";
      expect(value).not.toContain("super-secret");
    }
  });
});
