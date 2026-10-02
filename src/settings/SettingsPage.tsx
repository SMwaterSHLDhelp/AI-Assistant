import { addEventListener, removeEventListener, toaster } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  Focusable,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  showModal,
} from "@decky/ui";
import { useEffect, useState } from "react";
import {
  cancelOAuth,
  deleteProvider,
  getState,
  oauthStatus,
  saveProvider,
  saveSettings,
  startOAuth,
  testProvider,
} from "../api";
import { fieldValue } from "../form";
import { copyText } from "../steam";
import type { AppState, BackendEvent, ProviderInput, ProviderKindInfo, PublicProvider } from "../types";

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

interface Draft {
  id: string;
  kind: string;
  name: string;
  base_url: string;
  default_model: string;
  max_tokens: string;
  api_key: string;
  clear_api_key: boolean;
  oauth_client_id: string;
  oauth_client_secret: string;
  clear_oauth_secret: boolean;
  has_api_key: boolean;
  api_key_last4: string;
  has_oauth_secret: boolean;
  oauth_connected: boolean;
}

export function SettingsPage() {
  const [state, setState] = useState<AppState>(emptyState);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [oauth, setOauth] = useState({ status: "", message: "", userCode: "", url: "" });

  const report = (message: string) => {
    setError(message);
    toaster.toast({ title: "AI Assistant", body: message, duration: 6000 });
  };

  const load = async () => {
    try {
      const loaded = await getState();
      if (!loaded.ok) {
        report(loaded.error || "Could not load settings");
        return;
      }
      setState(loaded);
      if (!loaded.catalog || loaded.catalog.length === 0) {
        report("The provider list came back empty. Reopen settings, or reload the plugin.");
      }
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not load settings");
    }
  };

  useEffect(() => {
    void load();
    const listener = addEventListener<[BackendEvent]>("ai_assistant_event", (event) => {
      if (event.type !== "oauth") {
        return;
      }
      setOauth({
        status: event.status || "",
        message: event.message || "",
        userCode: event.user_code || "",
        url: event.verification_url || "",
      });
      if (event.status === "success") {
        void load();
      }
    });
    return () => removeEventListener("ai_assistant_event", listener);
  }, []);

  const kind = state.catalog.find((item) => item.kind === draft?.kind);

  const beginCreate = () => {
    const first = state.catalog[0];
    if (!first) {
      report("Provider types have not loaded yet. Reopen settings and try Add provider again.");
      return;
    }
    setDraft(blankDraft(first));
    setNotice("");
    setError("");
    setOauth({ status: "", message: "", userCode: "", url: "" });
  };

  const selectKind = (nextKind: ProviderKindInfo) => {
    setDraft((prev) => {
      if (!prev) {
        return blankDraft(nextKind);
      }
      const previous = state.catalog.find((item) => item.kind === prev.kind);
      return {
        ...prev,
        kind: nextKind.kind,
        name: !prev.name || prev.name === previous?.label ? nextKind.label : prev.name,
        base_url:
          !prev.base_url || prev.base_url === previous?.default_base_url ? nextKind.default_base_url : prev.base_url,
        default_model:
          !prev.default_model || prev.default_model === previous?.default_model
            ? nextKind.default_model
            : prev.default_model,
      };
    });
    setError("");
  };

  const beginEdit = (provider: PublicProvider) => {
    setDraft({
      id: provider.id,
      kind: provider.kind,
      name: provider.name,
      base_url: provider.base_url,
      default_model: provider.default_model,
      max_tokens: String(provider.max_tokens),
      api_key: "",
      clear_api_key: false,
      oauth_client_id: provider.oauth_client_id,
      oauth_client_secret: "",
      clear_oauth_secret: false,
      has_api_key: provider.has_api_key,
      api_key_last4: provider.api_key_last4,
      has_oauth_secret: provider.has_oauth_secret,
      oauth_connected: provider.oauth_connected,
    });
    setNotice("");
    setError("");
    void oauthStatus(provider.id).then((result) => {
      if (result.ok) {
        setOauth({
          status: result.status || "",
          message: result.message || "",
          userCode: result.user_code || "",
          url: result.verification_url || "",
        });
      }
    });
  };

  const save = async () => {
    if (!draft) {
      return;
    }
    const payload: ProviderInput = {
      kind: draft.kind,
      name: draft.name.trim(),
      base_url: draft.base_url.trim(),
      default_model: draft.default_model.trim(),
      max_tokens: Number(draft.max_tokens) || 1024,
      api_key: draft.clear_api_key ? "" : draft.api_key.trim() ? draft.api_key.trim() : null,
      oauth_client_id: draft.oauth_client_id.trim(),
      oauth_client_secret: draft.clear_oauth_secret
        ? ""
        : draft.oauth_client_secret.trim()
          ? draft.oauth_client_secret.trim()
          : null,
    };
    if (draft.id) {
      payload.id = draft.id;
    }
    let result;
    try {
      result = await saveProvider(payload);
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not save the provider");
      return;
    }
    if (!result.ok || !result.provider) {
      report(result.error || "Could not save the provider");
      return;
    }
    setError("");
    setNotice("Provider saved. Keys stay in the plugin settings folder and are not shown again.");
    await load();
    beginEdit(result.provider);
  };

  const saveDefaults = async () => {
    let result;
    try {
      result = await saveSettings({
        system_prompt: state.system_prompt,
        default_provider_id: state.default_provider_id,
        default_model: state.default_model,
      });
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not save defaults");
      return;
    }
    if (!result.ok) {
      report(result.error || "Could not save defaults");
      return;
    }
    setNotice("Defaults saved.");
    await load();
  };

  const test = async () => {
    if (!draft?.id) {
      setError("Save the provider before testing it");
      return;
    }
    let result;
    try {
      result = await testProvider(draft.id);
    } catch (err) {
      report(err instanceof Error ? err.message : "Connection failed");
      return;
    }
    if (!result.ok) {
      report(result.error || "Connection failed");
      return;
    }
    setError("");
    setNotice(result.message || "Connected");
    if (result.models && result.models.length > 0 && !draft.default_model) {
      setDraft({ ...draft, default_model: result.models[0] });
    }
  };

  const login = async (flow: "device" | "pkce" | "setup-token") => {
    if (!draft?.id) {
      setError("Save the provider before signing in");
      return;
    }
    setOauth({ status: "starting", message: "Contacting the provider…", userCode: "", url: "" });
    let result;
    try {
      result = await startOAuth(draft.id, flow);
    } catch (err) {
      report(err instanceof Error ? err.message : "Could not start sign-in");
      return;
    }
    if (!result.ok) {
      report(result.error || "Could not start sign-in");
      return;
    }
    setError("");
    setOauth({
      status: result.status || "pending",
      message: result.message || "",
      userCode: result.user_code || "",
      url: result.verification_url || "",
    });
  };

  return (
    <Focusable
      flow-children="column"
      style={{ padding: "16px 16px 48px", maxWidth: "900px", margin: "0 auto" }}
    >
      <PanelSection title="AI Assistant settings">
        <PanelSectionRow>
          <div>Credentials are stored on this Deck, mode 0600, and are never written to the plugin log.</div>
        </PanelSectionRow>
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

      <PanelSection title="Defaults">
        {state.providers.length === 0 ? (
          <PanelSectionRow>
            <div>No providers yet. Add one below, then choose it here.</div>
          </PanelSectionRow>
        ) : (
          state.providers.map((item) => (
            <ButtonItem
              key={item.id}
              layout="below"
              onClick={() =>
                setState((prev) => ({
                  ...prev,
                  default_provider_id: item.id,
                  default_model: item.default_model || prev.default_model,
                }))
              }
            >
              {state.default_provider_id === item.id ? `Default: ${item.name}` : `Use ${item.name}`}
            </ButtonItem>
          ))
        )}
        <PanelSectionRow>
          <TextField
            label="Default model"
            value={state.default_model}
            onChange={(event) => setState((prev) => ({ ...prev, default_model: fieldValue(event) }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="System prompt"
            description="Sent with every request. It is not shown as a chat bubble."
            value={state.system_prompt}
            onChange={(event) => setState((prev) => ({ ...prev, system_prompt: fieldValue(event) }))}
          />
        </PanelSectionRow>
        <ButtonItem layout="below" onClick={() => void saveDefaults()}>
          Save defaults
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Providers">
        {state.providers.map((provider) => (
          <ButtonItem key={provider.id} layout="below" onClick={() => beginEdit(provider)}>
            {`${provider.name} (${labelFor(state.catalog, provider.kind)})`}
          </ButtonItem>
        ))}
        <ButtonItem layout="below" onClick={beginCreate}>
          Add provider
        </ButtonItem>
      </PanelSection>

      {draft ? (
        <PanelSection title={draft.id ? "Edit provider" : "New provider"}>
          <PanelSectionRow>
            <div>{`Type: ${kind?.label || draft.kind}. Pick a type below. The highlighted choice is the one that will be saved.`}</div>
          </PanelSectionRow>
          {state.catalog.map((item) => (
            <ButtonItem key={item.kind} layout="below" onClick={() => selectKind(item)}>
              {item.kind === draft.kind ? `Selected: ${item.label}` : item.label}
            </ButtonItem>
          ))}
          {kind ? (
            <PanelSectionRow>
              <div>{kind.description}</div>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <TextField label="Name" value={draft.name} onChange={(event) => patchDraft(setDraft, { name: fieldValue(event) })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label={draft.kind === "claude_code" ? "Bridge URL" : "Base URL"}
              description={
                draft.kind === "claude_code"
                  ? "Leave empty to run Claude Code on this Deck. For a PC on your LAN, use http://that-pc:8765."
                  : undefined
              }
              value={draft.base_url}
              onChange={(event) => patchDraft(setDraft, { base_url: fieldValue(event) })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="Default model"
              value={draft.default_model}
              onChange={(event) => patchDraft(setDraft, { default_model: fieldValue(event) })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="Max tokens"
              mustBeNumeric
              value={draft.max_tokens}
              onChange={(event) => patchDraft(setDraft, { max_tokens: fieldValue(event) })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label={secretLabel(draft.kind, draft.base_url)}
              bIsPassword
              description={secretDescription(draft.kind, draft.base_url, draft.has_api_key, draft.api_key_last4)}
              value={draft.api_key}
              onChange={(event) => patchDraft(setDraft, { api_key: fieldValue(event), clear_api_key: false })}
            />
          </PanelSectionRow>
          {draft.has_api_key ? (
            <ButtonItem
              layout="below"
              onClick={() => {
                patchDraft(setDraft, { api_key: "", clear_api_key: true });
                setNotice("The saved API key will be removed when you press Save provider.");
              }}
            >
              Remove saved API key
            </ButtonItem>
          ) : null}
          {kind && kind.oauth === "claude_code" ? (
            <>
              <PanelSectionRow>
                <div>
                  Install Claude Code on this Deck from the official setup page, then sign in here or with claude login.
                  Remote mode runs bridge/claude_bridge.py on a PC instead. Use of Claude Code follows Anthropic's terms.
                </div>
              </PanelSectionRow>
              <ButtonItem layout="below" disabled={!draft.id || Boolean(draft.base_url.trim())} onClick={() => void login("setup-token")}>
                Sign in with setup-token
              </ButtonItem>
              {oauth.userCode ? (
                <PanelSectionRow>
                  <div>
                    <div>Code: {oauth.userCode}</div>
                    <ButtonItem layout="below" onClick={() => void copyText(oauth.userCode)}>
                      Copy code
                    </ButtonItem>
                  </div>
                </PanelSectionRow>
              ) : null}
              {oauth.url ? (
                <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(oauth.url)}>
                  Open verification page
                </ButtonItem>
              ) : null}
              {oauth.message ? (
                <PanelSectionRow>
                  <div>{oauth.message}</div>
                </PanelSectionRow>
              ) : null}
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void cancelOAuth(draft.id)}>
                Cancel sign-in
              </ButtonItem>
            </>
          ) : null}
          {kind && kind.oauth === "xai" ? (
            <>
              <PanelSectionRow>
                <div>
                  API key from the xAI console, or device-code sign-in for a SuperGrok or X Premium+ account. The
                  sign-in uses xAI's published device flow and the public Grok CLI client (the same one Hermes Agent
                  uses). There is no client secret to paste.
                </div>
              </PanelSectionRow>
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void login("device")}>
                Sign in with device code
              </ButtonItem>
              {oauth.userCode ? (
                <PanelSectionRow>
                  <div>
                    <div>Code: {oauth.userCode}</div>
                    <ButtonItem layout="below" onClick={() => void copyText(oauth.userCode)}>
                      Copy code
                    </ButtonItem>
                  </div>
                </PanelSectionRow>
              ) : null}
              {oauth.url ? (
                <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(oauth.url)}>
                  Open verification page
                </ButtonItem>
              ) : null}
              {oauth.message ? (
                <PanelSectionRow>
                  <div>{oauth.message}</div>
                </PanelSectionRow>
              ) : null}
              {draft.oauth_connected ? (
                <PanelSectionRow>
                  <div>xAI sign-in saved.</div>
                </PanelSectionRow>
              ) : null}
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void cancelOAuth(draft.id)}>
                Cancel sign-in
              </ButtonItem>
            </>
          ) : null}
          {kind && kind.oauth !== "none" && kind.oauth !== "claude_code" && kind.oauth !== "xai" ? (
            <>
              <PanelSectionRow>
                <TextField
                  label="OAuth client ID"
                  description="Required only for OAuth. API keys do not use this."
                  value={draft.oauth_client_id}
                  onChange={(event) => patchDraft(setDraft, { oauth_client_id: fieldValue(event) })}
                />
              </PanelSectionRow>
              {kind.oauth === "google" ? (
                <PanelSectionRow>
                  <TextField
                    label="OAuth client secret"
                    bIsPassword
                    description={
                      draft.has_oauth_secret
                        ? "A client secret is saved. Leave blank to keep it. Google's device flow needs it."
                        : "From your Google Cloud OAuth client. Needed for the device-code flow."
                    }
                    value={draft.oauth_client_secret}
                    onChange={(event) =>
                      patchDraft(setDraft, { oauth_client_secret: fieldValue(event), clear_oauth_secret: false })
                    }
                  />
                </PanelSectionRow>
              ) : null}
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void login("device")}>
                Sign in with device code
              </ButtonItem>
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void login("pkce")}>
                Sign in with PKCE on this Deck
              </ButtonItem>
              {oauth.userCode ? (
                <PanelSectionRow>
                  <div>
                    <div>Code: {oauth.userCode}</div>
                    <ButtonItem layout="below" onClick={() => void copyText(oauth.userCode)}>
                      Copy code
                    </ButtonItem>
                  </div>
                </PanelSectionRow>
              ) : null}
              {oauth.url ? (
                <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(oauth.url)}>
                  Open verification page
                </ButtonItem>
              ) : null}
              {oauth.message ? (
                <PanelSectionRow>
                  <div>{oauth.message}</div>
                </PanelSectionRow>
              ) : null}
              {draft.oauth_connected ? (
                <PanelSectionRow>
                  <div>OAuth token saved.</div>
                </PanelSectionRow>
              ) : null}
              <ButtonItem layout="below" disabled={!draft.id} onClick={() => void cancelOAuth(draft.id)}>
                Cancel sign-in
              </ButtonItem>
            </>
          ) : null}
          <ButtonItem layout="below" onClick={() => void save()}>
            Save provider
          </ButtonItem>
          <ButtonItem layout="below" disabled={!draft.id} onClick={() => void test()}>
            Test connection
          </ButtonItem>
          {draft.id ? (
            <ButtonItem
              layout="below"
              onClick={() => {
                const id = draft.id;
                try {
                  showModal(
                    <ConfirmModal
                      strTitle="Delete this provider?"
                      strDescription="The saved key and tokens for this provider will be removed."
                      strOKButtonText="Delete"
                      onOK={() => {
                        void (async () => {
                          try {
                            const result = await deleteProvider(id);
                            if (!result.ok) {
                              report(result.error || "Could not delete the provider");
                              return;
                            }
                            setDraft(null);
                            setNotice("Provider deleted.");
                            await load();
                          } catch (err) {
                            report(err instanceof Error ? err.message : "Could not delete the provider");
                          }
                        })();
                      }}
                    />,
                    window,
                  );
                } catch (err) {
                  report(err instanceof Error ? err.message : "Could not open the delete confirmation");
                }
              }}
            >
              Delete provider
            </ButtonItem>
          ) : null}
        </PanelSection>
      ) : null}
    </Focusable>
  );
}

function blankDraft(kind: ProviderKindInfo): Draft {
  return {
    id: "",
    kind: kind.kind,
    name: kind.label,
    base_url: kind.default_base_url,
    default_model: kind.default_model,
    max_tokens: "1024",
    api_key: "",
    clear_api_key: false,
    oauth_client_id: "",
    oauth_client_secret: "",
    clear_oauth_secret: false,
    has_api_key: false,
    api_key_last4: "",
    has_oauth_secret: false,
    oauth_connected: false,
  };
}

function labelFor(catalog: ProviderKindInfo[], kind: string): string {
  return catalog.find((item) => item.kind === kind)?.label || kind;
}

function secretLabel(kind: string, baseUrl: string): string {
  if (kind === "claude_code") {
    return baseUrl.trim() ? "Bridge shared secret" : "Claude Code token";
  }
  return "API key";
}

function secretDescription(kind: string, baseUrl: string, hasSecret: boolean, last4: string): string {
  const saved = hasSecret ? `Saved value ending in ${last4 || "••••"}. Leave blank to keep it. ` : "";
  if (kind === "claude_code" && baseUrl.trim()) {
    return `${saved}The secret you gave bridge/claude_bridge.py. This is not the Claude token.`;
  }
  if (kind === "claude_code") {
    return `${saved}Optional if this Deck is already signed in with claude login. Sign in below, or paste the token from claude setup-token.`;
  }
  if (kind === "xai") {
    return `${saved}From the xAI console. Leave blank if you sign in with the device code instead.`;
  }
  if (hasSecret) {
    return `Saved key ending in ${last4 || "••••"}. Leave blank to keep it.`;
  }
  return "Leave blank for local servers that do not need a key.";
}

function patchDraft(setDraft: (updater: (prev: Draft | null) => Draft | null) => void, patch: Partial<Draft>) {
  setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
}
