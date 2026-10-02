import { addEventListener, removeEventListener } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  showModal,
} from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { cancelChat, clearSession, getState, listModels, newSession, sendMessage, switchSession } from "../api";
import { copyText, newRequestId, runningGameName } from "../steam";
import type { AppState, BackendEvent, ChatMessage } from "../types";

const emptyState = (): AppState => ({
  catalog: [],
  providers: [],
  default_provider_id: "",
  default_model: "",
  system_prompt: "",
  current_session_id: "",
  sessions: [],
  messages: [],
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
  const requestRef = useRef<string | null>(null);
  const sessionRef = useRef("");

  useEffect(() => {
    sessionRef.current = state.current_session_id;
  }, [state.current_session_id]);

  useEffect(() => {
    const listener = addEventListener<[BackendEvent]>("ai_assistant_event", (event) => {
      if (event.type === "chat_delta" && event.request_id === requestRef.current && event.text) {
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
      if (event.type === "chat_done" && event.request_id === requestRef.current) {
        requestRef.current = null;
        setStreaming(false);
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
        setError(event.error || "The provider returned an error");
      }
    });
    return () => removeEventListener("ai_assistant_event", listener);
  }, []);

  useEffect(() => {
    void (async () => {
      const loaded = await getState();
      if (!loaded.ok) {
        setError(loaded.error || "Could not load AI Assistant");
        return;
      }
      setState(loaded);
      const initial = loaded.default_provider_id || loaded.providers[0]?.id || "";
      setProviderId(initial);
      const provider = loaded.providers.find((item) => item.id === initial);
      setModel(loaded.default_model || provider?.default_model || "");
    })();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setGame(runningGameName()), 2000);
    setGame(runningGameName());
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      const result = await listModels(providerId);
      if (!cancelled && result.ok && result.models) {
        setModels(result.models);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [providerId]);

  const providerOptions = state.providers.map((item) => ({
    label: item.name,
    data: item.id,
  }));
  const modelOptions = uniqueModels(models, model).map((item) => ({ label: item, data: item }));
  const sessionOptions = state.sessions.map((item) => ({
    label: item.title || "New chat",
    data: item.id,
  }));

  const send = async (aboutGame: string) => {
    if (streaming) {
      return;
    }
    if (!providerId) {
      setError("Add a provider in settings first");
      return;
    }
    const requestId = newRequestId();
    requestRef.current = requestId;
    setStreaming(true);
    setError("");
    const result = await sendMessage(providerId, model, draft, requestId, aboutGame);
    if (!result.ok) {
      requestRef.current = null;
      setStreaming(false);
      setError(result.error || "Could not send");
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
    const requestId = requestRef.current;
    if (requestId) {
      await cancelChat(requestId);
    }
  };

  const openSettings = () => {
    Navigation.Navigate("/ai-assistant/settings");
    Navigation.CloseSideMenus();
  };

  return (
    <>
      <PanelSection title="AI Assistant">
        {state.providers.length === 0 ? (
          <PanelSectionRow>
            <div>Add a provider to start chatting.</div>
          </PanelSectionRow>
        ) : (
          <>
            <DropdownItem
              label="Provider"
              menuLabel="Provider"
              rgOptions={providerOptions}
              selectedOption={providerId}
              onChange={(option) => {
                const next = String(option.data);
                setProviderId(next);
                const match = state.providers.find((item) => item.id === next);
                setModel(match?.default_model || "");
              }}
            />
            {modelOptions.length > 0 ? (
              <DropdownItem
                label="Model"
                menuLabel="Model"
                rgOptions={modelOptions}
                selectedOption={model || modelOptions[0].data}
                onChange={(option) => setModel(String(option.data))}
              />
            ) : null}
            <PanelSectionRow>
              <TextField label="Model id" value={model} onChange={(event) => setModel(event.target.value)} />
            </PanelSectionRow>
          </>
        )}
        {sessionOptions.length > 0 ? (
          <DropdownItem
            label="Conversation"
            menuLabel="Conversation"
            rgOptions={sessionOptions}
            selectedOption={state.current_session_id}
            onChange={(option) => {
              void (async () => {
                const result = await switchSession(String(option.data));
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
              })();
            }}
          />
        ) : null}
        <ButtonItem layout="below" onClick={() => void refreshSession(setState, setError, "new")}>
          New chat
        </ButtonItem>
        <ButtonItem layout="below" onClick={openSettings}>
          Provider settings
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Chat">
        {state.messages.length === 0 ? (
          <PanelSectionRow>
            <div>No messages yet. Type below, then press Send.</div>
          </PanelSectionRow>
        ) : (
          state.messages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
        {streaming ? (
          <PanelSectionRow>
            <div>Streaming…</div>
          </PanelSectionRow>
        ) : null}
        {error ? (
          <PanelSectionRow>
            <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title="Message">
        <PanelSectionRow>
          <TextField
            label="Ask"
            description="Opens the on-screen keyboard"
            value={draft}
            disabled={streaming}
            onChange={(event) => setDraft(event.target.value)}
          />
        </PanelSectionRow>
        {streaming ? (
          <ButtonItem layout="below" onClick={() => void stop()}>
            Stop
          </ButtonItem>
        ) : (
          <ButtonItem layout="below" disabled={!providerId} onClick={() => void send("")}>
            Send
          </ButtonItem>
        )}
        <ButtonItem
          layout="below"
          disabled={streaming || !game}
          description={game ? `Playing ${game}` : "No game is running"}
          onClick={() => void send(game)}
        >
          Ask about the current game
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

function MessageBubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "user";
  return (
    <PanelSectionRow>
      <div
        style={{
          width: "100%",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          padding: "6px 0",
        }}
      >
        <div style={{ opacity: 0.7, fontSize: "12px", marginBottom: "4px" }}>{mine ? "You" : "Assistant"}</div>
        <div>{message.content}</div>
        {!mine ? (
          <ButtonItem layout="below" onClick={() => void copyText(message.content)}>
            Copy
          </ButtonItem>
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

function uniqueModels(models: string[], current: string): string[] {
  const values = current ? [current, ...models] : models;
  return [...new Set(values.filter((item) => item))];
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
