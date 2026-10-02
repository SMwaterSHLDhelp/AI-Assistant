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

  const load = async () => {
    const loaded = await getState();
    if (!loaded.ok) {
      setError(loaded.error || "Could not load settings");
      return;
    }
    setState(loaded);
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
      return;
    }
    setDraft(blankDraft(first));
    setNotice("");
    setError("");
    setOauth({ status: "", message: "", userCode: "", url: "" });
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
    const result = await saveProvider(payload);
    if (!result.ok || !result.provider) {
      setError(result.error || "Could not save the provider");
      return;
    }
    setError("");
    setNotice("Provider saved. Keys stay in the plugin settings folder and are not shown again.");
    await load();
    beginEdit(result.provider);
  };

  const saveDefaults = async () => {
    const result = await saveSettings({
      system_prompt: state.system_prompt,
      default_provider_id: state.default_provider_id,
      default_model: state.default_model,
    });
    if (!result.ok) {
      setError(result.error || "Could not save defaults");
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
    const result = await testProvider(draft.id);
    if (!result.ok) {
      setError(result.error || "Connection failed");
      return;
    }
    setError("");
    setNotice(result.message || "Connected");
    if (result.models && result.models.length > 0 && !draft.default_model) {
      setDraft({ ...draft, default_model: result.models[0] });
    }
  };

  const login = async (flow: "device" | "pkce") => {
    if (!draft?.id) {
      setError("Save the provider before signing in");
      return;
    }
    setOauth({ status: "starting", message: "Contacting the provider…", userCode: "", url: "" });
    const result = await startOAuth(draft.id, flow);
    if (!result.ok) {
      setError(result.error || "Could not start sign-in");
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
    <div style={{ padding: "16px", maxWidth: "900px", margin: "0 auto" }}>
      <PanelSection title="AI Assistant settings">
        <PanelSectionRow>
          <div>Credentials are stored on this Deck, mode 0600, and are never written to the plugin log.</div>
        </PanelSectionRow>
        <ButtonItem layout="below" onClick={() => Navigation.NavigateBack()}>
          Back
        </ButtonItem>
      </PanelSection>

      <PanelSection title="Defaults">
        <DropdownItem
          label="Default provider"
          menuLabel="Default provider"
          rgOptions={
            state.providers.length > 0
              ? state.providers.map((item) => ({ label: item.name, data: item.id }))
              : [{ label: "None yet", data: "" }]
          }
          selectedOption={state.default_provider_id}
          disabled={state.providers.length === 0}
          onChange={(option) => {
            const id = String(option.data);
            const match = state.providers.find((item) => item.id === id);
            setState((prev) => ({
              ...prev,
              default_provider_id: id,
              default_model: match?.default_model || prev.default_model,
            }));
          }}
        />
        <PanelSectionRow>
          <TextField
            label="Default model"
            value={state.default_model}
            onChange={(event) => setState((prev) => ({ ...prev, default_model: event.target.value }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="System prompt"
            description="Sent with every request. It is not shown as a chat bubble."
            value={state.system_prompt}
            onChange={(event) => setState((prev) => ({ ...prev, system_prompt: event.target.value }))}
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
          <DropdownItem
            label="Type"
            menuLabel="Provider type"
            rgOptions={state.catalog.map((item) => ({ label: item.label, data: item.kind }))}
            selectedOption={draft.kind}
            onChange={(option) => {
              const nextKind = state.catalog.find((item) => item.kind === option.data);
              if (!nextKind) {
                return;
              }
              setDraft((prev) =>
                prev
                  ? {
                      ...prev,
                      kind: nextKind.kind,
                      base_url: prev.base_url && prev.base_url !== kind?.default_base_url ? prev.base_url : nextKind.default_base_url,
                      default_model: prev.default_model || nextKind.default_model,
                    }
                  : prev,
              );
            }}
          />
          {kind ? (
            <PanelSectionRow>
              <div>{kind.description}</div>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <TextField label="Name" value={draft.name} onChange={(event) => patchDraft(setDraft, { name: event.target.value })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="Base URL"
              value={draft.base_url}
              onChange={(event) => patchDraft(setDraft, { base_url: event.target.value })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="Default model"
              value={draft.default_model}
              onChange={(event) => patchDraft(setDraft, { default_model: event.target.value })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="Max tokens"
              mustBeNumeric
              value={draft.max_tokens}
              onChange={(event) => patchDraft(setDraft, { max_tokens: event.target.value })}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="API key"
              bIsPassword
              description={
                draft.has_api_key
                  ? `Saved key ending in ${draft.api_key_last4 || "••••"}. Leave blank to keep it.`
                  : "Leave blank for local servers that do not need a key."
              }
              value={draft.api_key}
              onChange={(event) => patchDraft(setDraft, { api_key: event.target.value, clear_api_key: false })}
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
          {kind && kind.oauth !== "none" ? (
            <>
              <PanelSectionRow>
                <TextField
                  label="OAuth client ID"
                  description="Required only for OAuth. API keys do not use this."
                  value={draft.oauth_client_id}
                  onChange={(event) => patchDraft(setDraft, { oauth_client_id: event.target.value })}
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
                      patchDraft(setDraft, { oauth_client_secret: event.target.value, clear_oauth_secret: false })
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
                showModal(
                  <ConfirmModal
                    strTitle="Delete this provider?"
                    strDescription="The saved key and tokens for this provider will be removed."
                    strOKButtonText="Delete"
                    onOK={() => {
                      void (async () => {
                        const result = await deleteProvider(id);
                        if (!result.ok) {
                          setError(result.error || "Could not delete the provider");
                          return;
                        }
                        setDraft(null);
                        setNotice("Provider deleted.");
                        await load();
                      })();
                    }}
                  />,
                );
              }}
            >
              Delete provider
            </ButtonItem>
          ) : null}
        </PanelSection>
      ) : null}

      {notice ? (
        <PanelSection title="Status">
          <PanelSectionRow>
            <div>{notice}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
      {error ? (
        <PanelSection title="Problem">
          <PanelSectionRow>
            <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
    </div>
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

function patchDraft(setDraft: (updater: (prev: Draft | null) => Draft | null) => void, patch: Partial<Draft>) {
  setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
}
