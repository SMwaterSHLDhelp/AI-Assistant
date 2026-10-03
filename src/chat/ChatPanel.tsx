import { addEventListener, removeEventListener, toaster } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  ModalRoot,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  showModal,
} from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import {
  cancelChat,
  clearSession,
  getState,
  listModels,
  lookAtScreen,
  newSession,
  pushToTalk,
  saveLastScreenshot,
  sendMessage,
  setGameContext,
  setHearingActivity,
  stopListening,
  stopSpeaking,
  switchSession,
} from "../api";
import { fieldValue } from "../form";
import { nextStep } from "../hints";
import { renderMarkdown } from "../markdown";
import { FirstRun, PRESET_KEY } from "../onboarding";
import { bindHearingChord, bindSleep } from "../hearing";
import { ModelPicker } from "../ModelPicker";
import { errorMessage, sleep, withRetry } from "../retry";
import { bindScreenChord, prepareScreenCapture, trySteamScreenshot, wantsScreenLook } from "../screenHelp";
import { copyText, newRequestId, runningGameName } from "../steam";
import type { AppState, BackendEvent, ChatMessage } from "../types";
import { defaultContext, defaultHearing, defaultVoice, defaultWeb } from "../types";
import type { NowPlaying } from "../types";
import { readLiveGame } from "../gameContext";

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
});

export function ChatPanel() {
  const [state, setState] = useState<AppState>(emptyState);
  const [providerId, setProviderId] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [game, setGame] = useState("");
  const [loading, setLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelReload, setModelReload] = useState(0);
  const [visionModels, setVisionModels] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const [searching, setSearching] = useState(false);
  const requestRef = useRef<string | null>(null);
  const streamSession = useRef("");
  const sessionRef = useRef("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const lookRef = useRef<(question?: string) => Promise<void>>(async () => {});
  const sleepingRef = useRef(false);

  useEffect(() => {
    sessionRef.current = state.current_session_id;
  }, [state.current_session_id]);

  useEffect(() => {
    const listener = addEventListener<[BackendEvent]>("deckling_event", (event) => {
      if (
        event.type === "chat_delta" &&
        event.request_id === requestRef.current &&
        event.text &&
        (!streamSession.current || streamSession.current === sessionRef.current)
      ) {
        const delta = event.text;
        const requestId = event.request_id;
        setState((prev) => {
          const messages = [...prev.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "assistant" && last.id === requestId) {
            messages[messages.length - 1] = { ...last, content: last.content + delta };
          } else {
            messages.push({
              id: requestId,
              role: "assistant",
              content: delta,
              created_at: Date.now() / 1000,
            });
          }
          return { ...prev, messages };
        });
        return;
      }
      if (event.type === "web" && event.request_id === requestRef.current) {
        setSearching(event.phase === "searching");
        return;
      }
      if (event.type === "chat_done" && event.request_id === requestRef.current) {
        requestRef.current = null;
        setStreaming(false);
        setSearching(false);
        if (event.session_id && event.session_id === sessionRef.current && event.messages) {
          setState((prev) => ({
            ...prev,
            messages: event.messages ?? prev.messages,
            sessions: event.sessions ?? prev.sessions,
          }));
        } else if (event.sessions) {
          setState((prev) => ({ ...prev, sessions: event.sessions ?? prev.sessions }));
        }
        return;
      }
      if (event.type === "chat_error" && event.request_id === requestRef.current) {
        requestRef.current = null;
        setStreaming(false);
        setSearching(false);
        setError(event.error || "The provider returned an error");
        return;
      }
      if (event.type === "hearing") {
        if (event.phase) {
          setState((prev) => ({
            ...prev,
            hearing: {
              ...prev.hearing,
              phase: event.phase || prev.hearing.phase,
              install_message:
                event.phase === "install" ? event.message || prev.hearing.install_message : prev.hearing.install_message,
            },
          }));
        }
        if (event.phase === "error" && event.message) {
          setError(nextStep(event.message));
        }
        if (event.phase === "sending" && event.request_id) {
          requestRef.current = event.request_id;
          setStreaming(true);
          const transcript = event.transcript || event.message || "";
          if (transcript) {
            setState((prev) => ({
              ...prev,
              messages: [
                ...prev.messages,
                {
                  id: `voice-${event.request_id}`,
                  role: "user",
                  content: transcript,
                  created_at: Date.now() / 1000,
                },
              ],
            }));
          }
        }
        if (event.phase === "screen" && event.transcript) {
          void lookRef.current(event.transcript);
        }
        if (event.phase === "cancelled") {
          setStreaming(false);
          requestRef.current = null;
          void getState().then((loaded) => {
            if (loaded.ok) {
              setState((prev) => ({ ...prev, messages: loaded.messages, sessions: loaded.sessions }));
            }
          });
        }
        return;
      }
      if (event.type === "speech") {
        setSpeaking(event.status === "started");
        if (event.status === "error" && event.error) {
          setError(event.error);
        }
      }
    });
    return () => removeEventListener("deckling_event", listener);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      let lastError = "Could not load Deckling";
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const loaded = await withRetry(() => getState(), 1);
          if (cancelled) {
            return;
          }
          if (loaded.ok) {
            setState({
              ...loaded,
              voice: { ...defaultVoice(), ...(loaded.voice || {}) },
              hearing: { ...defaultHearing(), ...(loaded.hearing || {}) },
              context: { ...defaultContext(), ...(loaded.context || {}) },
              game: loaded.game || null,
              suggestions: loaded.suggestions || [],
              web: { ...defaultWeb(), ...(loaded.web || {}) },
            });
            const initial = loaded.default_provider_id || loaded.providers[0]?.id || "";
            setProviderId(initial);
            const provider = loaded.providers.find((item) => item.id === initial);
            setModel(loaded.default_model || provider?.default_model || "");
            setError("");
            setLoading(false);
            return;
          }
          lastError = loaded.error || lastError;
          if (loaded.providers) {
            setState((prev) => ({
              ...prev,
              ...loaded,
              voice: { ...defaultVoice(), ...(loaded.voice || prev.voice) },
              hearing: { ...defaultHearing(), ...(loaded.hearing || prev.hearing) },
              context: { ...defaultContext(), ...(loaded.context || prev.context) },
              game: loaded.game ?? prev.game,
              suggestions: loaded.suggestions || prev.suggestions,
              web: { ...defaultWeb(), ...(loaded.web || prev.web) },
            }));
          }
        } catch (err) {
          lastError = errorMessage(err, lastError);
        }
        if (attempt < 2) {
          await sleep(400 * (attempt + 1));
        }
      }
      if (!cancelled) {
        setLoading(false);
        setError(lastError);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => bindScreenChord(() => void lookRef.current()), []);

  useEffect(() => {
    const offChord = bindHearingChord(() => {
      void pushToTalk();
    });
    const offSleep = bindSleep((sleeping) => {
      sleepingRef.current = sleeping;
      void setHearingActivity(Boolean(runningGameName()), sleeping);
    });
    const timer = window.setInterval(() => {
      void setHearingActivity(Boolean(runningGameName()), sleepingRef.current);
    }, 5000);
    void setHearingActivity(Boolean(runningGameName()), sleepingRef.current);
    return () => {
      offChord();
      offSleep();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setGame(runningGameName()), 2000);
    setGame(runningGameName());
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let lastKey = "";
    const tick = async () => {
      const snapshot = await readLiveGame();
      if (cancelled) {
        return;
      }
      const key = [
        snapshot.appid,
        snapshot.name,
        snapshot.exe,
        snapshot.launch_options,
        snapshot.rich_presence,
        snapshot.achievements_unlocked,
      ].join("|");
      if (key === lastKey) {
        return;
      }
      lastKey = key;
      if (!snapshot.name) {
        setState((prev) => ({ ...prev, game: null, suggestions: [] }));
        try {
          await setGameContext({ ...snapshot });
        } catch {
          // The card is already clear. The next poll retries the backend.
        }
        return;
      }
      const local: NowPlaying = {
        appid: snapshot.appid,
        name: snapshot.name,
        rich_presence: snapshot.rich_presence,
        achievements_unlocked: snapshot.achievements_unlocked,
        achievements_total: snapshot.achievements_total,
        capsule: "",
        emulator: "",
        shortcut: snapshot.shortcut,
        sources: snapshot.sources,
      };
      try {
        const result = await setGameContext({ ...snapshot });
        if (cancelled) {
          return;
        }
        if (result.ok) {
          setState((prev) => ({
            ...prev,
            game: result.game === undefined ? local : result.game,
            suggestions: result.suggestions || [],
            context: result.context ? { ...defaultContext(), ...result.context } : prev.context,
          }));
          return;
        }
      } catch {
        // Store lookup can fail offline. The Steam fields still fill the card.
      }
      if (!cancelled) {
        setState((prev) => ({ ...prev, game: local }));
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    setModelsError("");
    void (async () => {
      try {
        const result = await withRetry(() => listModels(providerId), 2);
        if (cancelled) {
          return;
        }
        if (!result.ok) {
          setModelsError(result.error || "Could not list models");
          setModels([]);
          setVisionModels([]);
          return;
        }
        const found = result.models || [];
        setModels(found);
        setVisionModels(result.vision_models || []);
        setModel((current) => current || found[0] || "");
      } catch (err) {
        if (!cancelled) {
          setModelsError(errorMessage(err, "Could not list models"));
        }
      } finally {
        if (!cancelled) {
          setModelsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [providerId, modelReload]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [state.messages, streaming]);

  const look = async (question: string, nextModel?: string) => {
    if (streaming) {
      return;
    }
    if (!providerId) {
      setError("Add a provider in settings first");
      return;
    }
    if (!state.voice.screen_capture) {
      setError("Screen capture is turned off in settings.");
      return;
    }
    const modelId = nextModel || model;
    if (nextModel) {
      setModel(nextModel);
    }
    const requestId = newRequestId();
    requestRef.current = requestId;
    setStreaming(true);
    setError("");
    setSuggestions([]);
    try {
      await stopSpeaking();
      const shot = await prepareScreenCapture(() => Navigation.CloseSideMenus(), sleep, trySteamScreenshot);
      const result = await lookAtScreen(providerId, modelId, question, requestId, runningGameName(), shot || "", true);
      if (!result.ok) {
        requestRef.current = null;
        setStreaming(false);
        setError(result.error || "Could not look at the screen");
        setSuggestions(result.suggestions || []);
        return;
      }
      setDraft("");
      if (result.messages) {
        setState((prev) => ({
          ...prev,
          messages: result.messages ?? prev.messages,
          sessions: result.sessions ?? prev.sessions,
        }));
      }
    } catch (err) {
      requestRef.current = null;
      setStreaming(false);
      setError(errorMessage(err, "Could not look at the screen"));
    }
  };
  lookRef.current = (question?: string) => look(question ?? draft);

  const send = async (aboutGame: string, text = draft) => {
    if (streaming) {
      return;
    }
    if (wantsScreenLook(text)) {
      await look(text);
      return;
    }
    if (!providerId) {
      setError(nextStep("Add a provider in settings first"));
      return;
    }
    const requestId = newRequestId();
    requestRef.current = requestId;
    streamSession.current = sessionRef.current;
    setStreaming(true);
    setError("");
    let result;
    try {
      result = await sendMessage(providerId, model, text, requestId, aboutGame);
    } catch (err) {
      requestRef.current = null;
      setStreaming(false);
      setError(nextStep(errorMessage(err, "Could not send. Check the provider, then try again.")));
      return;
    }
    if (!result.ok) {
      requestRef.current = null;
      setStreaming(false);
      setError(nextStep(result.error || "Could not send. Check the provider, then try again."));
      return;
    }
    setDraft("");
    if (result.messages) {
      setState((prev) => ({
        ...prev,
        messages: result.messages ?? prev.messages,
        sessions: result.sessions ?? prev.sessions,
      }));
    }
  };

  const stop = async () => {
    setSpeaking(false);
    try {
      await stopSpeaking();
      const requestId = requestRef.current;
      if (requestId) {
        await cancelChat(requestId);
      }
    } catch (err) {
      setError(nextStep(errorMessage(err, "Could not stop. Try again.")));
    }
  };

  const openSettings = (preset?: string) => {
    if (preset) {
      try {
        sessionStorage.setItem(PRESET_KEY, preset);
      } catch {
        // The settings page still has the same presets.
      }
    }
    Navigation.Navigate("/deckling/settings");
    Navigation.CloseSideMenus();
  };

  const currentProvider = state.providers.find((item) => item.id === providerId);
  const micLabel =
    speaking
      ? "Speaking"
      : state.hearing.phase === "listening"
        ? "Listening"
        : state.hearing.phase === "recording"
          ? "Hearing you"
          : state.hearing.phase === "transcribing"
            ? "Transcribing"
            : state.hearing.phase === "paused"
              ? "Paused"
              : "Mic";

  const openSwitcher = () => {
    const handle = { close: () => undefined as void };
    const opened = showModal(
      <ModalRoot onCancel={() => handle.close()} bDisableBackgroundDismiss>
        <PanelSection title="Provider and model">
          {state.providers.map((item) => (
            <ButtonItem
              key={item.id}
              layout="below"
              onClick={() => {
                setProviderId(item.id);
                setModel(item.default_model || "");
              }}
            >
              {providerId === item.id ? `Using ${item.name}` : item.name}
            </ButtonItem>
          ))}
          <ModelPicker
            label="Model"
            models={models}
            value={model}
            onChange={setModel}
            onRefresh={() => setModelReload((value) => value + 1)}
            loading={modelsLoading}
            error={modelsError}
            visionIds={visionModels}
          />
          <ButtonItem layout="below" onClick={() => handle.close()}>
            Done
          </ButtonItem>
        </PanelSection>
      </ModalRoot>,
      window,
    );
    handle.close = () => opened.Close();
  };

  const openChats = () => {
    const handle = { close: () => undefined as void };
    const opened = showModal(
      <ModalRoot onCancel={() => handle.close()}>
        <PanelSection title="Chats">
          {state.sessions.map((item) => (
            <ButtonItem
              key={item.id}
              layout="below"
              onClick={() => {
                void (async () => {
                  try {
                    const result = await switchSession(item.id);
                    if (!result.ok || !result.messages || !result.current_session_id) {
                      setError(result.error || "Could not open that conversation");
                      return;
                    }
                    setState((prev) => ({
                      ...prev,
                      current_session_id: result.current_session_id || prev.current_session_id,
                      messages: result.messages || [],
                      sessions: result.sessions || prev.sessions,
                    }));
                    handle.close();
                  } catch (err) {
                    setError(errorMessage(err, "Could not open that conversation"));
                  }
                })();
              }}
            >
              {state.current_session_id === item.id ? `Open: ${item.title || "New chat"}` : item.title || "New chat"}
            </ButtonItem>
          ))}
          <ButtonItem layout="below" onClick={() => handle.close()}>
            Close
          </ButtonItem>
        </PanelSection>
      </ModalRoot>,
      window,
    );
    handle.close = () => opened.Close();
  };

  return (
    <>
      <style>{`
        .deckling-bubble p { margin: 0 0 8px; }
        .deckling-bubble ul { margin: 0 0 8px; padding-left: 18px; }
        .deckling-bubble pre { margin: 0 0 8px; padding: 8px; overflow-x: auto; background: #0e141b; border-radius: 6px; }
        .deckling-bubble code { font-size: 14px; }
      `}</style>
      <PanelSection title="Deckling">
        {state.game ? <NowPlayingCard game={state.game} /> : null}
        <PanelSectionRow>
          <div style={{ fontSize: "14px", opacity: 0.85 }}>A tiny companion in your menu.</div>
        </PanelSectionRow>
        {loading ? (
          <PanelSectionRow>
            <div>Loading…</div>
          </PanelSectionRow>
        ) : null}
        {state.providers.length === 0 && !loading ? (
          <FirstRun onPreset={(kind) => openSettings(kind)} onCustom={() => openSettings()} />
        ) : null}
        {state.providers.length > 0 ? (
          <ButtonItem layout="below" onClick={openSwitcher}>
            {`${currentProvider?.name || "Provider"} · ${model || "choose a model"}`}
          </ButtonItem>
        ) : null}
        {state.sessions.length > 0 ? (
          <ButtonItem layout="below" onClick={openChats}>
            {state.sessions.find((item) => item.id === state.current_session_id)?.title || "Chats"}
          </ButtonItem>
        ) : null}
      </PanelSection>

      <PanelSection title="Chat">
        {state.messages.length === 0 ? (
          <PanelSectionRow>
            <div style={{ fontSize: "16px" }}>
              {state.providers.length === 0
                ? "Add a provider and I'll be right here."
                : "I'm here. Ask about the game, or tell me to look at the screen."}
            </div>
          </PanelSectionRow>
        ) : (
          state.messages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
        {searching ? (
          <PanelSectionRow>
            <div style={{ fontSize: "16px" }}>Searching the web…</div>
          </PanelSectionRow>
        ) : null}
        {streaming ? (
          <PanelSectionRow>
            <div style={{ fontSize: "16px" }}>Deckling is writing…</div>
          </PanelSectionRow>
        ) : null}
        <div ref={bottomRef} />
        {error ? (
          <PanelSectionRow>
            <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
          </PanelSectionRow>
        ) : null}
        {suggestions.map((id) => (
          <ButtonItem key={id} layout="below" onClick={() => void look(draft, id)}>
            {`Switch to ${id}`}
          </ButtonItem>
        ))}
        <ButtonItem layout="below" onClick={() => void look(draft || "What am I looking at, and what should I do next?")}>
          Look at my screen
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => void refreshSession(setState, setError, "new")}>
          New chat
        </ButtonItem>
        <ButtonItem layout="below" disabled={!providerId || streaming} onClick={() => void send("", "Summarize this conversation in a few sentences.")}>
          Summarize
        </ButtonItem>
        {state.suggestions.map((prompt) => (
          <ButtonItem key={prompt} layout="below" disabled={!providerId || streaming} onClick={() => void send("", prompt)}>
            {prompt}
          </ButtonItem>
        ))}
      </PanelSection>

      <PanelSection title="Message">
        {streaming ? (
          <ButtonItem layout="below" onClick={() => void stop()}>
            Stop generation
          </ButtonItem>
        ) : null}
        <PanelSectionRow>
          <TextField
            key="chat-ask"
            label="Ask"
            description="Opens the on-screen keyboard"
            value={draft}
            disabled={streaming}
            onChange={(event) => setDraft(fieldValue(event))}
          />
        </PanelSectionRow>
        {streaming ? null : (
          <ButtonItem layout="below" disabled={!providerId} onClick={() => void send("")}>
            Send
          </ButtonItem>
        )}
        <ButtonItem layout="below" disabled={streaming || !game} description={game ? `Playing ${game}` : "No game is running"} onClick={() => void send(game)}>
          Ask about the current game
        </ButtonItem>
        <ButtonItem
          layout="below"
          disabled={streaming}
          onClick={() => {
            if (speaking) {
              void stop();
              return;
            }
            if (!state.hearing.ptt_enabled) {
              setError("Push to talk is off. Turn it on under Voice in settings.");
              return;
            }
            void pushToTalk().catch((err) => setError(errorMessage(err, "Could not use the microphone.")));
          }}
        >
          {micLabel}
        </ButtonItem>
        {state.hearing.wake_enabled ? (
          <ButtonItem
            layout="below"
            onClick={() =>
              void stopListening().then((result) => {
                if (result.hearing) {
                  setState((prev) => ({ ...prev, hearing: { ...prev.hearing, ...result.hearing } }));
                }
              })
            }
          >
            Stop listening
          </ButtonItem>
        ) : null}
        <ButtonItem layout="below" onClick={() => openSettings()}>
          Provider settings
        </ButtonItem>
        <ButtonItem
          layout="below"
          onClick={() => {
            void (async () => {
              const saved = await saveLastScreenshot();
              if (!saved.ok) {
                setError(saved.error || "Nothing to save yet. Look at the screen first.");
                return;
              }
              setError("");
              toaster.toast({ title: "Deckling", body: "Saved the screenshot on this Deck.", duration: 2000 });
            })();
          }}
        >
          Save screenshot
        </ButtonItem>
        <ButtonItem
          layout="below"
          disabled={!lastAssistant(state.messages)}
          onClick={() => {
            const text = lastAssistant(state.messages);
            if (text) {
              void copyText(text);
            }
          }}
        >
          Copy last reply
        </ButtonItem>
        <ButtonItem
          layout="below"
          onClick={() =>
            showModal(
              <ConfirmModal
                strTitle="Clear this chat?"
                strDescription="Messages in this conversation will be deleted on this Deck."
                strOKButtonText="Clear"
                onOK={() => void refreshSession(setState, setError, "clear")}
              />,
            )
          }
        >
          Clear chat
        </ButtonItem>
      </PanelSection>
    </>
  );
}

function NowPlayingCard({ game }: { game: NowPlaying }) {
  const progress =
    game.achievements_total && game.achievements_unlocked != null
      ? `Achievements ${game.achievements_unlocked}/${game.achievements_total}`
      : "";
  return (
    <PanelSectionRow>
      <div style={{ display: "flex", gap: "10px", alignItems: "center", padding: "4px 0 8px" }}>
        {game.capsule ? (
          <img src={game.capsule} alt="" width={92} height={43} style={{ borderRadius: "4px", objectFit: "cover" }} />
        ) : (
          <div
            aria-hidden
            style={{ width: "44px", height: "44px", borderRadius: "8px", background: "#1b3a4a", flex: "0 0 auto" }}
          />
        )}
        <div>
          <div style={{ fontSize: "12px", letterSpacing: "0.04em", opacity: 0.7 }}>Now playing</div>
          <div style={{ fontSize: "16px" }}>{game.name}</div>
          {game.rich_presence ? <div style={{ fontSize: "14px" }}>{game.rich_presence}</div> : null}
          {progress ? <div style={{ fontSize: "14px" }}>{progress}</div> : null}
        </div>
      </div>
    </PanelSectionRow>
  );
}

function openSource(url: string) {
  const steam = (window as unknown as { SteamClient?: { System?: Record<string, unknown> } }).SteamClient;
  const system = steam?.System;
  const opener = system?.OpenInSystemBrowser || system?.OpenURLInClient;
  if (typeof opener === "function") {
    (opener as (target: string) => void).call(system, url);
    return;
  }
  window.open(url, "_blank", "noopener");
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "user";
  return (
    <PanelSectionRow>
      <div
        className="deckling-bubble"
        style={{
          width: "100%",
          wordBreak: "break-word",
          padding: "8px 10px",
          margin: "6px 0",
          borderRadius: "8px",
          fontSize: "16px",
          lineHeight: 1.4,
          background: mine ? "#1b3a4a" : "#15202b",
          borderLeft: mine ? "3px solid #7fd1c3" : "3px solid #8b9bb4",
        }}
      >
        <div style={{ opacity: 0.7, fontSize: "13px", marginBottom: "4px" }}>{mine ? "You" : "Deckling"}</div>
        {mine ? (
          <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
        ) : (
          <div dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }} />
        )}
        {message.sources && message.sources.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" }}>
            {message.sources.map((source) => (
              <button
                key={source.url}
                type="button"
                onClick={() => openSource(source.url)}
                style={{
                  fontSize: "13px",
                  padding: "4px 8px",
                  borderRadius: "999px",
                  border: "1px solid #7fd1c3",
                  background: "transparent",
                  color: "#7fd1c3",
                }}
              >
                {source.title || source.url}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </PanelSectionRow>
  );
}

function lastAssistant(messages: ChatMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant" && messages[index].content) {
      return messages[index].content;
    }
  }
  return "";
}

async function refreshSession(
  setState: (updater: (prev: AppState) => AppState) => void,
  setError: (value: string) => void,
  action: "new" | "clear",
) {
  const result = action === "new" ? await newSession() : await clearSession();
  if (!result.ok || !result.messages) {
    setError(result.error || "Could not update the conversation");
    return;
  }
  setState((prev) => ({
    ...prev,
    current_session_id: result.current_session_id || prev.current_session_id,
    messages: result.messages || [],
    sessions: result.sessions ?? prev.sessions,
  }));
}
