import { addEventListener, removeEventListener } from "@decky/api";
import { ButtonItem, DialogButton, Navigation, PanelSection, PanelSectionRow, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import {
  cancelOAuth,
  deleteProvider,
  listModels,
  oauthStatus,
  saveProvider,
  startOAuth,
  testProvider,
} from "../api";
import { PROVIDER_KINDS, kindInfo } from "../catalog";
import { fieldValue } from "../form";
import { ModelPicker } from "../ModelPicker";
import { reportFailure, reportSaved } from "../notify";
import { errorMessage, withRetry } from "../retry";
import { copyText } from "../steam";
import type { BackendEvent, ProviderInput, ProviderKindInfo, PublicProvider } from "../types";
import { SettingsDialog } from "./dialog";

export interface Draft {
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

export function blankDraft(kind: ProviderKindInfo): Draft {
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

export function draftFromProvider(provider: PublicProvider): Draft {
  return {
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
  };
}

/**
 * Provider details stay inside this dialog. Keystrokes update this state only,
 * so the settings route does not redraw and the Steam keyboard keeps its field.
 */
export function ProviderEditor({
  initial,
  onClose,
  onSaved,
  onError,
}: {
  initial: Draft;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [oauth, setOauth] = useState({ status: "", message: "", userCode: "", url: "" });
  const [modelChoices, setModelChoices] = useState<string[]>([]);
  const [visionChoices, setVisionChoices] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelReload, setModelReload] = useState(0);
  const kind = kindInfo(draft.kind);

  useEffect(() => {
    if (!initial.id) {
      return;
    }
    void oauthStatus(initial.id).then((result) => {
      if (!result.ok) {
        return;
      }
      setOauth({
        status: result.status || "",
        message: result.message || "",
        userCode: result.user_code || "",
        url: result.verification_url || "",
      });
    });
  }, [initial.id]);

  useEffect(() => {
    const listener = addEventListener<[BackendEvent]>("deckling_event", (event) => {
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
        setDraft((prev) => ({ ...prev, oauth_connected: true }));
      }
    });
    return () => removeEventListener("deckling_event", listener);
  }, []);

  useEffect(() => {
    const providerId = draft.id;
    if (!providerId) {
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
          const message = result.error || "Could not list models";
          setModelsError(message);
          setModelChoices([]);
          setVisionChoices([]);
          reportFailure(message);
          return;
        }
        const found = result.models || [];
        setModelChoices(found);
        setVisionChoices(result.vision_models || []);
        setDraft((prev) => {
          if (!prev || prev.id !== providerId || prev.default_model.trim() || found.length === 0) {
            return prev;
          }
          return { ...prev, default_model: found[0] };
        });
        requestAnimationFrame(() => {
          document.getElementById("deckling-model-picker")?.scrollIntoView({ block: "nearest" });
        });
      } catch (err) {
        if (!cancelled) {
          const message = errorMessage(err, "Could not list models");
          setModelsError(message);
          reportFailure(message);
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
  }, [draft.id, modelReload]);

  const selectKind = (nextKind: ProviderKindInfo) => {
    setDraft((prev) => {
      const previous = kindInfo(prev.kind);
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

  const save = async () => {
    const name = draft.name.trim();
    if (!name || name.length > 80) {
      const message = "Provider name must be 1-80 characters";
      setError(message);
      onError(message);
      return;
    }
    const payload: ProviderInput = {
      kind: draft.kind,
      name,
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
      const message = err instanceof Error ? err.message : "Could not save the provider";
      setError(message);
      onError(message);
      return;
    }
    if (!result.ok || !result.provider) {
      const message = result.error || "Could not save the provider";
      setError(message);
      onError(message);
      return;
    }
    setError("");
    setModelsError("");
    setNotice("Provider saved. Keys stay in the plugin settings folder and are not shown again.");
    reportSaved("Provider saved. Loading models.");
    setDraft(draftFromProvider(result.provider));
    setModelReload((value) => value + 1);
    await onSaved();
  };

  const test = async () => {
    if (!draft.id) {
      setError("Save the provider before testing it");
      return;
    }
    let result;
    try {
      result = await testProvider(draft.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed";
      setError(message);
      onError(message);
      return;
    }
    if (!result.ok) {
      const message = result.error || "Connection failed";
      setError(message);
      onError(message);
      return;
    }
    setError("");
    setNotice(result.message || "Connected");
    if (result.models && result.models.length > 0) {
      setModelChoices(result.models);
      setVisionChoices(result.vision_models || []);
      setModelsError("");
      if (!draft.default_model) {
        setDraft({ ...draft, default_model: result.models[0] });
      }
    }
  };

  const login = async (flow: "device" | "pkce" | "setup-token") => {
    if (!draft.id) {
      setError("Save the provider before signing in");
      return;
    }
    setOauth({ status: "starting", message: "Contacting the provider…", userCode: "", url: "" });
    let result;
    try {
      result = await startOAuth(draft.id, flow);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not start sign-in";
      setError(message);
      onError(message);
      return;
    }
    if (!result.ok) {
      const message = result.error || "Could not start sign-in";
      setError(message);
      onError(message);
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

  const remove = async () => {
    try {
      const result = await deleteProvider(draft.id);
      if (!result.ok) {
        const message = result.error || "Could not delete the provider";
        setError(message);
        onError(message);
        return;
      }
      await onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not delete the provider";
      setError(message);
      onError(message);
    }
  };

  return (
    <SettingsDialog
      title={draft.id ? "Edit provider" : "New provider"}
      onClose={onClose}
      footer={
        <>
          <DialogButton onClick={() => void save()}>Save provider</DialogButton>
          <DialogButton onClick={onClose}>Cancel</DialogButton>
        </>
      }
    >
      <PanelSection title={draft.id ? "Edit provider" : "New provider"}>
        <PanelSectionRow>
          <div>{`Type: ${kind?.label || draft.kind}. The highlighted choice is the one that will be saved.`}</div>
        </PanelSectionRow>
        {PROVIDER_KINDS.map((item) => (
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
          <TextField
            key="provider-name"
            label="Name"
            value={draft.name}
            onChange={(event) => setDraft((prev) => ({ ...prev, name: fieldValue(event) }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            key="provider-url"
            label={draft.kind === "claude_code" ? "Bridge URL" : "Base URL"}
            value={draft.base_url}
            onChange={(event) => setDraft((prev) => ({ ...prev, base_url: fieldValue(event) }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <div>
            {draft.kind === "claude_code"
              ? "Leave the bridge URL empty to run Claude Code on this Deck. For a PC on your LAN, use http://that-pc:8765."
              : "Leave Model blank if you want. Save provider stores this and then loads the model list."}
          </div>
        </PanelSectionRow>
        <div id="deckling-model-picker">
        <ModelPicker
          label="Model"
          models={modelChoices}
          value={draft.default_model}
          onChange={(model) => setDraft((prev) => ({ ...prev, default_model: model }))}
          onRefresh={() => {
            if (!draft.id) {
              setModelsError("Save the provider before loading models.");
              return;
            }
            setModelReload((value) => value + 1);
          }}
          loading={modelsLoading}
          error={modelsError}
          visionIds={visionChoices}
        />
        </div>
        <PanelSectionRow>
          <TextField
            key="provider-tokens"
            label="Max tokens"
            mustBeNumeric
            value={draft.max_tokens}
            onChange={(event) => setDraft((prev) => ({ ...prev, max_tokens: fieldValue(event) }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            key="provider-key"
            label="API key"
            bIsPassword
            value={draft.api_key}
            onChange={(event) => setDraft((prev) => ({ ...prev, api_key: fieldValue(event), clear_api_key: false }))}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <div>{secretDescription(draft.kind, draft.base_url, draft.has_api_key, draft.api_key_last4)}</div>
        </PanelSectionRow>
        {draft.has_api_key ? (
          <ButtonItem
            layout="below"
            onClick={() => {
              setDraft((prev) => ({ ...prev, api_key: "", clear_api_key: true }));
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
                Remote mode runs bridge/deckling_bridge.py on a PC instead. Use of Claude Code follows Anthropic's terms.
              </div>
            </PanelSectionRow>
            <ButtonItem layout="below" disabled={!draft.id || Boolean(draft.base_url.trim())} onClick={() => void login("setup-token")}>
              Sign in with setup-token
            </ButtonItem>
          </>
        ) : null}
        {kind && kind.oauth === "xai" ? (
          <>
            <PanelSectionRow>
              <div>
                API key from the xAI console, or device-code sign-in for a SuperGrok or X Premium+ account. There is no
                client secret to paste.
              </div>
            </PanelSectionRow>
            <ButtonItem layout="below" disabled={!draft.id} onClick={() => void login("device")}>
              Sign in with device code
            </ButtonItem>
          </>
        ) : null}
        {kind && kind.oauth !== "none" && kind.oauth !== "claude_code" && kind.oauth !== "xai" ? (
          <>
            <PanelSectionRow>
              <TextField
                key="provider-oauth-id"
                label="OAuth client ID"
                value={draft.oauth_client_id}
                onChange={(event) => setDraft((prev) => ({ ...prev, oauth_client_id: fieldValue(event) }))}
              />
            </PanelSectionRow>
            {kind.oauth === "google" ? (
              <PanelSectionRow>
                <TextField
                  key="provider-oauth-secret"
                  label="OAuth client secret"
                  bIsPassword
                  value={draft.oauth_client_secret}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      oauth_client_secret: fieldValue(event),
                      clear_oauth_secret: false,
                    }))
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
          </>
        ) : null}
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
            <div>Sign-in saved.</div>
          </PanelSectionRow>
        ) : null}
        {kind && kind.oauth !== "none" ? (
          <ButtonItem layout="below" disabled={!draft.id} onClick={() => void cancelOAuth(draft.id)}>
            Cancel sign-in
          </ButtonItem>
        ) : null}
        {error ? (
          <PanelSectionRow>
            <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
          </PanelSectionRow>
        ) : null}
        {notice ? (
          <PanelSectionRow>
            <div>{notice}</div>
          </PanelSectionRow>
        ) : null}
        <ButtonItem layout="below" disabled={!draft.id} onClick={() => void test()}>
          Test connection
        </ButtonItem>
        {draft.id && !confirmDelete ? (
          <ButtonItem layout="below" onClick={() => setConfirmDelete(true)}>
            Delete provider
          </ButtonItem>
        ) : null}
        {confirmDelete ? (
          <>
            <PanelSectionRow>
              <div>Delete this provider and its saved key?</div>
            </PanelSectionRow>
            <ButtonItem layout="below" onClick={() => void remove()}>
              Delete
            </ButtonItem>
            <ButtonItem layout="below" onClick={() => setConfirmDelete(false)}>
              Keep provider
            </ButtonItem>
          </>
        ) : null}
      </PanelSection>
    </SettingsDialog>
  );
}

function secretDescription(kind: string, baseUrl: string, hasSecret: boolean, last4: string): string {
  const saved = hasSecret ? `Saved value ending in ${last4 || "••••"}. Leave blank to keep it. ` : "";
  if (kind === "claude_code" && baseUrl.trim()) {
    return `${saved}The secret you gave bridge/deckling_bridge.py. This is not the Claude token.`;
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
