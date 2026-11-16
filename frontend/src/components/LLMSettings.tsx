import type { LLMSettings } from "../types/search";

interface Props {
  settings: LLMSettings;
  apiKey: string;
  onChange: (patch: Partial<LLMSettings>) => void;
  onApiKeyChange: (key: string) => void;
}

export function LLMSettingsPanel({
  settings,
  apiKey,
  onChange,
  onApiKeyChange,
}: Props) {
  const isOpenAI = settings.provider === "openai-compatible";
  const keyRequired = isOpenAI;
  const configured = Boolean(settings.base_url.trim() && settings.model.trim());

  return (
    <section aria-label="LLM settings" data-testid="llm-settings" className="rail-section">
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Model</h2>
        <span className={`token truncate ${configured ? "text-primary-dark" : "text-ink-faint"}`}>
          {configured ? settings.model : "not set"}
        </span>
      </div>

      <div className="mt-3 space-y-3">
        <label className="block">
          <span className="rail-label mb-1 block">Provider</span>
          <select
            value={settings.provider}
            onChange={(e) =>
              onChange({ provider: e.target.value as LLMSettings["provider"] })
            }
            className="field"
          >
            <option value="ollama">Ollama server</option>
            <option value="openai-compatible">OpenAI-compatible</option>
          </select>
        </label>

        <label className="block">
          <span className="rail-label mb-1 block">
            Base URL {isOpenAI ? "(usually ends in /v1)" : "(any Ollama server)"}
          </span>
          <input
            value={settings.base_url}
            onChange={(e) => onChange({ base_url: e.target.value })}
            placeholder={
              isOpenAI
                ? "https://api.example.com/v1"
                : "https://your-host.example.com/ollama"
            }
            className="field"
          />
        </label>

        <label className="block">
          <span className="rail-label mb-1 block">Model</span>
          <input
            value={settings.model}
            onChange={(e) => onChange({ model: e.target.value })}
            placeholder={isOpenAI ? "gpt-4o-mini" : "qwen3:32b"}
            className="field"
          />
        </label>

        <label className="block" data-testid="api-key-field">
          <span className="rail-label mb-1 block">
            API key{" "}
            <span className="normal-case tracking-normal text-ink-faint">
              {keyRequired
                ? "(required, kept in memory only)"
                : "(optional — only if your server requires auth)"}
            </span>
          </span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            autoComplete="off"
            placeholder={keyRequired ? "sk-..." : "leave empty if not needed"}
            className="field"
          />
        </label>
      </div>

      <p className="mt-4 text-[12px] leading-[1.5] tracking-fine text-ink-faint">
        {isOpenAI
          ? "The key stays in memory for the request and is never written to disk or a log."
          : "Any Ollama host works — hosted or a local install. The URL you enter is the one used; nothing is assumed."}
      </p>
    </section>
  );
}
