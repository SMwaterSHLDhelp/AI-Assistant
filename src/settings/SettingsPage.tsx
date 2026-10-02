import { toaster } from "@decky/api";
import { ButtonItem, Navigation, PanelSection, PanelSectionRow, TextField, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import { getState, saveSettings } from "../api";
import { PROVIDER_KINDS, kindInfo } from "../catalog";
import { fieldValue } from "../form";
import { errorMessage, sleep, withRetry } from "../retry";
import type { AppState, OkResult, PublicProvider } from "../types";
import { defaultHearing, defaultVoice } from "../types";
import { ProviderEditor, blankDraft, draftFromProvider } from "./ProviderEditor";
import { HearingSection } from "./HearingSection";
import { VoiceSection } from "./VoiceSection";

const emptyState = (): AppState => ({
  catalog: [],
  providers: [],
  default_provider_id: "",
  default_model: "",
  system_prompt: "",
  current_session_id: "",
  sessions: [],
  messages: [],
  voice: defaultVoice(),
  hearing: defaultHearing(),
});

export function SettingsPage() {
  const [state, setState] = useState<AppState>(emptyState);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const report = (message: string) => {
    setError(message);
    toaster.toast({ title: "Deckling", body: message, duration: 6000 });
  };

  const applyLoaded = (loaded: Partial<AppState> & OkResult) => {
    setState((prev) => ({
      ...prev,
      providers: loaded.providers ?? prev.providers,
      default_provider_id: loaded.default_provider_id ?? prev.default_provider_id,
      default_model: loaded.default_model ?? prev.default_model,
      system_prompt: loaded.system_prompt ?? prev.system_prompt,
      current_session_id: loaded.current_session_id ?? prev.current_session_id,
      sessions: loaded.sessions ?? prev.sessions,
      messages: loaded.messages ?? prev.messages,
      voice: { ...defaultVoice(), ...(loaded.voice || prev.voice) },
      hearing: { ...defaultHearing(), ...(loaded.hearing || prev.hearing) },
    }));
  };

  const load = async () => {
    setLoading(true);
    let lastError = "Could not load settings";
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const loaded = await withRetry(() => getState(), 1);
        applyLoaded(loaded);
        if (loaded.ok) {
          setError("");
          setLoading(false);
          return;
        }
        lastError = loaded.error || lastError;
      } catch (err) {
        lastError = errorMessage(err, lastError);
      }
      if (attempt < 2) {
        await sleep(400 * (attempt + 1));
      }
    }
    setLoading(false);
    report(lastError);
  };

  useEffect(() => {
    void load();
  }, []);

  const openEditor = (provider?: PublicProvider) => {
    const initial = provider ? draftFromProvider(provider) : blankDraft(PROVIDER_KINDS[0]);
    let opened: { Close: () => void } | undefined;
    try {
      opened = showModal(
        <ProviderEditor
          initial={initial}
          onClose={() => opened?.Close()}
          onSaved={load}
          onError={report}
        />,
        window,
      );
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not open the provider dialog");
    }
  };

  return (
    <div style={{ padding: "16px 16px 48px", maxWidth: "900px", margin: "0 auto" }}>
      <PanelSection title="Deckling settings">
        <PanelSectionRow>
          <div>
            Credentials are stored on this Deck, mode 0600, and are never written to the plugin log. If an older copy is
            still in the Decky plugin list, uninstall that entry after your providers show up here.
          </div>
        </PanelSectionRow>
        {loading ? (
          <PanelSectionRow>
            <div>Loading settings…</div>
          </PanelSectionRow>
        ) : null}
        <ButtonItem layout="below" onClick={() => Navigation.NavigateBack()}>
          Back
        </ButtonItem>
      </PanelSection>

      {error ? (
        <PanelSection title="Problem">
          <PanelSectionRow>
            <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
      {notice ? (
        <PanelSection title="Status">
          <PanelSectionRow>
            <div>{notice}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      <DefaultsSection
        providers={state.providers}
        defaultProviderId={state.default_provider_id}
        defaultModel={state.default_model}
        systemPrompt={state.system_prompt}
        onSaved={load}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
        onError={report}
      />

      <HearingSection
        hearing={state.hearing}
        onHearing={(hearing) => setState((prev) => ({ ...prev, hearing }))}
        onError={report}
      />

      <VoiceSection
        voice={state.voice}
        onVoice={(voice) => setState((prev) => ({ ...prev, voice }))}
        onError={report}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
      />

      <PanelSection title="Providers">
        {state.providers.map((provider) => (
          <ButtonItem key={provider.id} layout="below" onClick={() => openEditor(provider)}>
            {`${provider.name} (${kindInfo(provider.kind)?.label || provider.kind})`}
          </ButtonItem>
        ))}
        <ButtonItem layout="below" onClick={() => openEditor()}>
          Add provider
        </ButtonItem>
      </PanelSection>
    </div>
  );
}

function DefaultsSection({
  providers,
  defaultProviderId,
  defaultModel,
  systemPrompt,
  onSaved,
  onNotice,
  onError,
}: {
  providers: PublicProvider[];
  defaultProviderId: string;
  defaultModel: string;
  systemPrompt: string;
  onSaved: () => Promise<void>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [providerId, setProviderId] = useState(defaultProviderId);
  const [model, setModel] = useState(defaultModel);
  const [prompt, setPrompt] = useState(systemPrompt);

  useEffect(() => {
    setProviderId(defaultProviderId);
    setModel(defaultModel);
    setPrompt(systemPrompt);
  }, [defaultProviderId, defaultModel, systemPrompt]);

  const save = async () => {
    let result;
    try {
      result = await saveSettings({
        system_prompt: prompt,
        default_provider_id: providerId,
        default_model: model,
      });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save defaults");
      return;
    }
    if (!result.ok) {
      onError(result.error || "Could not save defaults");
      return;
    }
    onNotice("Defaults saved.");
    await onSaved();
  };

  return (
    <PanelSection title="Defaults">
      {providers.length === 0 ? (
        <PanelSectionRow>
          <div>No providers yet. Add one below, then choose it here.</div>
        </PanelSectionRow>
      ) : (
        providers.map((item) => (
          <ButtonItem
            key={item.id}
            layout="below"
            onClick={() => {
              setProviderId(item.id);
              setModel(item.default_model || model);
            }}
          >
            {providerId === item.id ? `Default: ${item.name}` : `Use ${item.name}`}
          </ButtonItem>
        ))
      )}
      <PanelSectionRow>
        <TextField
          key="default-model"
          label="Default model"
          value={model}
          onChange={(event) => setModel(fieldValue(event))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          key="system-prompt"
          label="System prompt"
          value={prompt}
          onChange={(event) => setPrompt(fieldValue(event))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <div>The system prompt is sent with every request. It is not shown as a chat bubble.</div>
      </PanelSectionRow>
      <ButtonItem layout="below" onClick={() => void save()}>
        Save defaults
      </ButtonItem>
    </PanelSection>
  );
}
