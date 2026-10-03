import { Navigation, PanelSection, PanelSectionRow, TextField, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import {
  deleteProvider,
  getDiagnostics,
  getHealth,
  getState,
  saveChats,
  saveContext,
  saveSettings,
  saveVoice,
  saveWeb,
  subscribeFailures,
  testProvider,
  writeDiagnostics,
} from "../api";
import { PROVIDER_KINDS, kindInfo } from "../catalog";
import { DeckRow } from "../DeckRow";
import { fieldValue } from "../form";
import { FirstRun, PRESET_KEY, QUICK_PRESETS, presetBaseUrl } from "../onboarding";
import { errorMessage, sleep, withRetry } from "../retry";
import { copyText } from "../steam";
import type { AppState, ContextSettings, OkResult, PublicProvider, WebSettings } from "../types";
import { defaultChats, defaultContext, defaultHearing, defaultVoice, defaultWeb } from "../types";
import { SettingsDialog } from "./dialog";
import { ProviderEditor, blankDraft, draftFromProvider, type Draft } from "./ProviderEditor";
import { HearingSection } from "./HearingSection";
import { VoiceSection } from "./VoiceSection";

const SEARCH_ORDER = ["duckduckgo", "searxng", "brave", "tavily", "serper"];

function backendUnreachable(message: string): boolean {
  return /backend not responding|timed out/i.test(message);
}
const SEARCH_LABEL: Record<string, string> = {
  duckduckgo: "DuckDuckGo",
  searxng: "SearXNG",
  brave: "Brave",
  tavily: "Tavily",
  serper: "Serper",
};

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
  context: defaultContext(),
  game: null,
  suggestions: [],
  web: defaultWeb(),
  chats: defaultChats(),
});

export function SettingsPage() {
  const [state, setState] = useState<AppState>(emptyState);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [voiceOffer, setVoiceOffer] = useState(false);
  const [pendingDelete, setPendingDelete] = useState("");
  const [healthLine, setHealthLine] = useState("Backend: checking…");
  const [healthOk, setHealthOk] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const report = (message: string) => {
    setError(message);
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
      context: { ...defaultContext(), ...(loaded.context || prev.context) },
      game: loaded.game ?? prev.game,
      suggestions: loaded.suggestions ?? prev.suggestions,
      web: { ...defaultWeb(), ...(loaded.web || prev.web) },
      chats: { ...defaultChats(), ...(loaded.chats || prev.chats) },
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
        if (backendUnreachable(lastError)) {
          break;
        }
      } catch (err) {
        lastError = errorMessage(err, lastError);
        if (backendUnreachable(lastError)) {
          break;
        }
      }
      if (attempt < 2) {
        await sleep(400 * (attempt + 1));
      }
    }
    setLoading(false);
    report(lastError);
  };

  const refreshHealth = async () => {
    const health = await getHealth();
    if (!health.ok) {
      setHealthOk(false);
      setHealthLine(health.error || "Backend is not connected.");
      return;
    }
    setHealthOk(true);
    setHealthLine(health.version ? `Backend: connected v${health.version}` : "Backend: connected");
  };

  const openDraft = (initial: Draft, typeLocked = false) => {
    const wasEmpty = state.providers.length === 0;
    const handle = { close: () => undefined as void };
    try {
      const opened = showModal(
        <ProviderEditor
          initial={initial}
          typeLocked={typeLocked}
          onClose={() => handle.close()}
          onSaved={async () => {
            await load();
            if (wasEmpty) {
              setVoiceOffer(true);
            }
          }}
          onError={report}
        />,
        window,
      );
      handle.close = () => opened.Close();
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not open the provider dialog");
    }
  };

  const openEditor = (provider?: PublicProvider) => {
    const initial = provider ? draftFromProvider(provider) : blankDraft(PROVIDER_KINDS[0]);
    openDraft(initial);
  };

  const openPreset = (kind: string) => {
    const info = kindInfo(kind) || PROVIDER_KINDS[0];
    const initial = blankDraft(info);
    const url = presetBaseUrl(kind);
    if (url) {
      initial.base_url = url;
    }
    const preset = QUICK_PRESETS.find((item) => item.kind === kind);
    if (preset && (kind === "ollama" || kind === "llamacpp")) {
      initial.name = preset.title;
    }
    openDraft(initial, true);
  };

  useEffect(() => {
    const unsubscribe = subscribeFailures((message) => setError(message));
    void refreshHealth();
    void load().then(() => {
      try {
        const kind = sessionStorage.getItem(PRESET_KEY);
        if (kind) {
          sessionStorage.removeItem(PRESET_KEY);
          openPreset(kind);
        }
      } catch {
        // sessionStorage can be blocked. The presets on this page still work.
      }
    });
    return unsubscribe;
  }, []);

  const openDefaults = () => {
    const handle = { close: () => undefined as void };
    const opened = showModal(
      <DefaultsSection
        providers={state.providers}
        defaultProviderId={state.default_provider_id}
        defaultModel={state.default_model}
        systemPrompt={state.system_prompt}
        onSaved={load}
        onClose={() => handle.close()}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
        onError={report}
      />,
      window,
    );
    handle.close = () => opened.Close();
  };

  const test = async (provider: PublicProvider) => {
    setNotice("");
    try {
      const result = await testProvider(provider.id);
      if (!result.ok) {
        report(result.error || "Connection failed. Check the address and try Test again.");
      } else {
        setError("");
        setNotice(result.message || "Connected.");
      }
    } catch (err) {
      report(errorMessage(err, "Connection failed. Check the address and try Test again."));
    }
    await load();
  };

  const remove = async (providerId: string) => {
    try {
      const result = await deleteProvider(providerId);
      if (!result.ok) {
        report(result.error || "Could not delete that provider.");
        return;
      }
      setPendingDelete("");
      setNotice("Provider deleted.");
      await load();
    } catch (err) {
      report(errorMessage(err, "Could not delete that provider."));
    }
  };

  const patchContext = async (patch: Partial<ContextSettings>) => {
    try {
      const result = await saveContext(patch);
      if (!result.ok || !result.context) {
        report(result.error || "Could not save game context");
        return;
      }
      setState((prev) => ({ ...prev, context: { ...defaultContext(), ...result.context } }));
    } catch (err) {
      report(errorMessage(err, "Could not save game context"));
    }
  };

  const patchWeb = async (patch: Record<string, unknown>) => {
    try {
      const result = await saveWeb(patch);
      if (!result.ok || !result.web) {
        report(result.error || "Could not save web lookup");
        return;
      }
      setState((prev) => ({ ...prev, web: { ...defaultWeb(), ...result.web } }));
    } catch (err) {
      report(errorMessage(err, "Could not save web lookup"));
    }
  };

  const openSearch = () => {
    const handle = { close: () => undefined as void };
    const opened = showModal(
      <SearchSetup
        web={state.web}
        onClose={() => handle.close()}
        onSave={(patch) => {
          void patchWeb(patch);
          handle.close();
        }}
      />,
      window,
    );
    handle.close = () => opened.Close();
  };

  const cycleSearch = () => {
    const index = SEARCH_ORDER.indexOf(state.web.provider);
    const next = SEARCH_ORDER[(index + 1) % SEARCH_ORDER.length];
    void patchWeb({ provider: next });
  };

  const setScreen = async (enabled: boolean) => {
    try {
      const result = await saveVoice({ screen_capture: enabled });
      if (!result.ok || !result.voice) {
        report(result.error || "Could not save screen help");
        return;
      }
      setState((prev) => ({ ...prev, voice: result.voice || prev.voice }));
    } catch (err) {
      report(errorMessage(err, "Could not save screen help"));
    }
  };

  return (
    <div style={{ padding: "8px 16px 24px", width: "100%", boxSizing: "border-box" }}>
      <PanelSection title="Deckling">
        <PanelSectionRow>
          <div style={{ color: healthOk ? "#3dd68c" : "#f2b8b5", fontSize: "16px" }}>{healthLine}</div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "15px" }}>A tiny companion for this Deck. B returns to the previous page.</div>
        </PanelSectionRow>
        {loading ? (
          <PanelSectionRow>
            <div>Loading settings…</div>
          </PanelSectionRow>
        ) : null}
        <DeckRow layout="below" onClick={() => Navigation.NavigateBack()}>
          Back
        </DeckRow>
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

      {state.providers.length === 0 ? <FirstRun onPreset={openPreset} onCustom={() => openEditor()} /> : null}
      {voiceOffer ? (
        <PanelSection title="Voice setup">
          <PanelSectionRow>
            <div>Optional. Deckling can listen for “hey jarvis”. The model downloads onto this Deck the first time you turn it on.</div>
          </PanelSectionRow>
          <DeckRow
            layout="below"
            onClick={() => {
              setVoiceOffer(false);
              document.getElementById("deckling-voice")?.scrollIntoView();
            }}
          >
            Set up voice later
          </DeckRow>
        </PanelSection>
      ) : null}

      <PanelSection title="Providers">
        {state.providers.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            pendingDelete={pendingDelete === provider.id}
            onEdit={() => openEditor(provider)}
            onTest={() => void test(provider)}
            onAskDelete={() => setPendingDelete(provider.id)}
            onCancelDelete={() => setPendingDelete("")}
            onDelete={() => void remove(provider.id)}
          />
        ))}
        {state.providers.length > 0 ? (
          <DeckRow layout="below" onClick={() => openEditor()}>
            Add provider
          </DeckRow>
        ) : null}
      </PanelSection>

      <div id="deckling-voice">
        <HearingSection
          hearing={state.hearing}
          onHearing={(hearing) => setState((prev) => ({ ...prev, hearing }))}
          onError={report}
        />
      </div>

      <VoiceSection
        voice={state.voice}
        onVoice={(voice) => setState((prev) => ({ ...prev, voice }))}
        onError={report}
        onNotice={(message) => {
          setError("");
          setNotice(message);
        }}
      />

      <PanelSection title="Screen help">
        <PanelSectionRow>
          <div>Screenshots go only to the provider you picked, and only when you ask about the screen. They are not saved unless you press Save screenshot.</div>
        </PanelSectionRow>
        <DeckRow layout="below" onClick={() => void setScreen(!state.voice.screen_capture)}>
          {state.voice.screen_capture ? "Screen capture: on" : "Screen capture: off"}
        </DeckRow>
      </PanelSection>

      <PanelSection title="Privacy">
        <PanelSectionRow>
          <div>
            Keys stay in this Deck's settings folder, mode 0600, and are not written to the log. Microphone audio stays
            on the Deck and is deleted after each line unless debug audio is on. Game context is sent only to the
            provider you picked, and only while sharing is on. Web lookup, when it is on, sends the search query and
            the pages the model opens to that same provider. If an older copy is still in the Decky plugin list,
            uninstall that entry after your providers show up here.
          </div>
        </PanelSectionRow>
        <DeckRow layout="below" onClick={() => void patchContext({ share_game_context: !state.context.share_game_context })}>
          {state.context.share_game_context ? "Share game context with AI: on" : "Share game context with AI: off"}
        </DeckRow>
        {state.context.share_game_context ? (
          <>
            <DeckRow layout="below" onClick={() => void patchContext({ include_achievements: !state.context.include_achievements })}>
              {state.context.include_achievements ? "Include achievements: on" : "Include achievements: off"}
            </DeckRow>
            <DeckRow layout="below" onClick={() => void patchContext({ include_playtime: !state.context.include_playtime })}>
              {state.context.include_playtime ? "Include playtime: on" : "Include playtime: off"}
            </DeckRow>
          </>
        ) : null}
        <DeckRow layout="below" onClick={() => void patchWeb({ enabled: !state.web.enabled })}>
          {state.web.enabled ? "Web lookup: on" : "Web lookup: off"}
        </DeckRow>
        {state.web.enabled ? (
          <>
            <DeckRow layout="below" onClick={cycleSearch}>
              {`Search: ${SEARCH_LABEL[state.web.provider] || "DuckDuckGo"}`}
            </DeckRow>
            {state.web.provider !== "duckduckgo" ? (
              <DeckRow layout="below" onClick={openSearch}>
                Edit search setup
              </DeckRow>
            ) : null}
          </>
        ) : null}
      </PanelSection>

      <PanelSection title="Advanced">
        <PanelSectionRow>
          <div>The default provider, model, and system prompt. Typing happens in a dialog so the Steam keyboard stays put.</div>
        </PanelSectionRow>
        <DeckRow layout="below" onClick={openDefaults}>
          Edit defaults
        </DeckRow>
        <DeckRow
          layout="below"
          onClick={() => {
            const next = state.chats.keep === 20 ? 40 : state.chats.keep === 40 ? 80 : 20;
            void saveChats({ keep: next }).then((result) => {
              if (!result.ok || !result.chats) {
                report(result.error || "Could not save chat history");
                return;
              }
              setState((prev) => ({
                ...prev,
                chats: { ...defaultChats(), ...result.chats },
                sessions: result.sessions || prev.sessions,
              }));
            });
          }}
        >
          {`Keep chats: ${state.chats.keep}`}
        </DeckRow>
        <DeckRow
          layout="below"
          onClick={() => {
            void saveChats({ remember_model: !state.chats.remember_model }).then((result) => {
              if (!result.ok || !result.chats) {
                report(result.error || "Could not save chat history");
                return;
              }
              setState((prev) => ({ ...prev, chats: { ...defaultChats(), ...result.chats } }));
            });
          }}
        >
          {state.chats.remember_model ? "Remember model per chat: on" : "Remember model per chat: off"}
        </DeckRow>
        <DeckRow layout="below" onClick={() => setShowDiagnostics((open) => !open)}>
          {showDiagnostics ? "Hide diagnostics" : "Diagnostics"}
        </DeckRow>
        {showDiagnostics ? <DiagnosticsPanel /> : null}
      </PanelSection>
    </div>
  );
}

function DiagnosticsPanel() {
  const [lines, setLines] = useState<string[]>([]);
  const [note, setNote] = useState("");
  useEffect(() => {
    void getDiagnostics().then((result) => {
      if (!result.ok) {
        setNote(result.error || "Could not read the log");
        return;
      }
      setLines(result.lines || []);
    });
  }, []);
  const text = (lines.length ? lines : ["No log lines yet."]).slice(-30).join("\n");
  return (
    <>
      <PanelSectionRow>
        <div style={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "13px" }}>{text}</div>
      </PanelSectionRow>
      <DeckRow layout="below" onClick={() => void copyText(text)}>
        Copy diagnostics
      </DeckRow>
      <DeckRow
        layout="below"
        onClick={() => {
          void writeDiagnostics().then((result) => {
            setNote(result.ok && result.path ? `Saved ${result.path}` : result.error || "Could not write the diagnostics file");
          });
        }}
      >
        Save diagnostics to home
      </DeckRow>
      {note ? (
        <PanelSectionRow>
          <div>{note}</div>
        </PanelSectionRow>
      ) : null}
    </>
  );
}

function ProviderCard({
  provider,
  pendingDelete,
  onEdit,
  onTest,
  onAskDelete,
  onCancelDelete,
  onDelete,
}: {
  provider: PublicProvider;
  pendingDelete: boolean;
  onEdit: () => void;
  onTest: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
}) {
  const status = provider.connection_status || "unknown";
  const color = status === "connected" ? "#3dd68c" : status === "error" ? "#f2b8b5" : "#8b9bb4";
  const label = status === "connected" ? "Connected" : status === "error" ? "Needs attention" : "Not tested";
  return (
    <>
      <PanelSectionRow>
        <div style={{ padding: "8px 0 2px" }}>
          <div style={{ fontSize: "16px" }}>
            <span
              aria-label={label}
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                borderRadius: "10px",
                background: color,
                marginRight: "8px",
              }}
            />
            {provider.name}
          </div>
          <div style={{ opacity: 0.8, fontSize: "14px" }}>
            {`${kindInfo(provider.kind)?.label || provider.kind} · ${provider.default_model || "no model yet"}`}
          </div>
          {provider.connection_detail ? <div style={{ fontSize: "14px" }}>{provider.connection_detail}</div> : null}
        </div>
      </PanelSectionRow>
      <DeckRow layout="below" onClick={onEdit}>
        {`Edit ${provider.name}`}
      </DeckRow>
      <DeckRow layout="below" onClick={onTest}>
        {`Test ${provider.name}`}
      </DeckRow>
      {pendingDelete ? (
        <>
          <DeckRow layout="below" onClick={onDelete}>
            Delete
          </DeckRow>
          <DeckRow layout="below" onClick={onCancelDelete}>
            Keep provider
          </DeckRow>
        </>
      ) : (
        <DeckRow layout="below" onClick={onAskDelete}>
          {`Delete ${provider.name}`}
        </DeckRow>
      )}
    </>
  );
}

function DefaultsSection({
  providers,
  defaultProviderId,
  defaultModel,
  systemPrompt,
  onSaved,
  onClose,
  onNotice,
  onError,
}: {
  providers: PublicProvider[];
  defaultProviderId: string;
  defaultModel: string;
  systemPrompt: string;
  onSaved: () => Promise<void>;
  onClose: () => void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [providerId, setProviderId] = useState(defaultProviderId);
  const [model, setModel] = useState(defaultModel);
  const [prompt, setPrompt] = useState(systemPrompt);

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
    onClose();
  };

  return (
    <SettingsDialog
      title="Defaults"
      onClose={onClose}
      onOK={() => void save()}
      footer={
        <>
          <DeckRow onClick={() => void save()}>Save defaults</DeckRow>
          <DeckRow onClick={onClose}>Cancel</DeckRow>
        </>
      }
    >
      <PanelSection title="Defaults">
        {providers.length === 0 ? (
          <PanelSectionRow>
            <div>No providers yet. Add one, then choose it here.</div>
          </PanelSectionRow>
        ) : (
          providers.map((item) => (
            <DeckRow
              key={item.id}
              layout="below"
              onClick={() => {
                setProviderId(item.id);
                setModel(item.default_model || model);
              }}
            >
              {providerId === item.id ? `Default: ${item.name}` : `Use ${item.name}`}
            </DeckRow>
          ))
        )}
        <PanelSectionRow>
          <TextField key="default-model" label="Default model" value={model} onChange={(event) => setModel(fieldValue(event))} />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField key="system-prompt" label="System prompt" value={prompt} onChange={(event) => setPrompt(fieldValue(event))} />
        </PanelSectionRow>
        <PanelSectionRow>
          <div>The system prompt is sent with every request. It is not shown as a chat bubble.</div>
        </PanelSectionRow>
      </PanelSection>
    </SettingsDialog>
  );
}

function SearchSetup({
  web,
  onClose,
  onSave,
}: {
  web: WebSettings;
  onClose: () => void;
  onSave: (patch: Record<string, string>) => void;
}) {
  const [url, setUrl] = useState(web.searxng_url);
  const [key, setKey] = useState("");
  const keyField =
    web.provider === "brave" ? "brave_key" : web.provider === "tavily" ? "tavily_key" : web.provider === "serper" ? "serper_key" : "";
  const save = () => {
    const patch: Record<string, string> = {};
    if (web.provider === "searxng") {
      patch.searxng_url = url;
    }
    if (keyField && key.trim()) {
      patch[keyField] = key.trim();
    }
    onSave(patch);
  };
  const hint =
    web.provider === "searxng"
      ? "Paste the SearXNG instance URL."
      : "Paste the API key for this search provider. It stays on this Deck.";
  return (
    <SettingsDialog
      title="Search setup"
      onClose={onClose}
      onOK={save}
      footer={
        <>
          <DeckRow onClick={save}>Save</DeckRow>
          <DeckRow onClick={onClose}>Cancel</DeckRow>
        </>
      }
    >
      <PanelSection title="Search setup">
        <PanelSectionRow>
          <div>{hint}</div>
        </PanelSectionRow>
        {web.provider === "searxng" ? (
          <PanelSectionRow>
            <TextField
              key="web-url"
              label="SearXNG URL"
              description="Example: https://search.example.com"
              value={url}
              onChange={(event) => setUrl(fieldValue(event))}
            />
          </PanelSectionRow>
        ) : null}
        {keyField ? (
          <PanelSectionRow>
            <TextField
              key="web-key"
              label="API key"
              description="Stored with your other keys. Leave blank to keep the current key."
              value={key}
              onChange={(event) => setKey(fieldValue(event))}
            />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    </SettingsDialog>
  );
}
