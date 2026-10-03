import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { kindInfo } from "./catalog";

export const PRESET_KEY = "deckling-preset";

export const QUICK_PRESETS: { kind: string; title: string; hint: string }[] = [
  {
    kind: "ollama",
    title: "Ollama on my PC",
    hint: "Replace 192.168.1.20 with that PC's address. Port 11434 is Ollama's default.",
  },
  {
    kind: "llamacpp",
    title: "llama.cpp on my PC",
    hint: "Replace 192.168.1.20 with that PC's address. Port 8080 is llama.cpp's default.",
  },
  { kind: "openai", title: "OpenAI", hint: "Paste an API key from the OpenAI platform." },
  { kind: "gemini", title: "Gemini", hint: "Paste an AI Studio key, or sign in after saving." },
  { kind: "xai", title: "Grok", hint: "Paste an xAI key, or use the device-code sign-in after saving." },
  { kind: "anthropic", title: "Claude", hint: "Paste an Anthropic API key. A Claude subscription uses Claude Code instead." },
];

export function presetBaseUrl(kind: string): string | undefined {
  if (kind === "ollama") {
    return "http://192.168.1.20:11434";
  }
  if (kind === "llamacpp") {
    return "http://192.168.1.20:8080/v1";
  }
  return kindInfo(kind)?.default_base_url;
}

export function FirstRun({
  onPreset,
  onCustom,
}: {
  onPreset: (kind: string) => void;
  onCustom: () => void;
}) {
  return (
    <PanelSection title="Welcome">
      <PanelSectionRow>
        <div style={{ fontSize: "18px", marginBottom: "6px" }}>Hi, I'm Deckling.</div>
        <div>Add your first provider. I can then chat, listen, and look at the game with you.</div>
      </PanelSectionRow>
      {QUICK_PRESETS.map((preset) => (
        <ButtonItem key={preset.kind} layout="below" description={preset.hint} onClick={() => onPreset(preset.kind)}>
          {preset.title}
        </ButtonItem>
      ))}
      <ButtonItem layout="below" onClick={onCustom}>
        Add provider
      </ButtonItem>
    </PanelSection>
  );
}
