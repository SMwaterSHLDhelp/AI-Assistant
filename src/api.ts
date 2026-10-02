import { callable } from "@decky/api";
import type {
  AppState,
  HearingSettings,
  OkResult,
  ProviderInput,
  PublicProvider,
  SessionSummary,
  VoiceSettings,
} from "./types";

export const getState = callable<[], AppState & OkResult>("get_state");
export const saveProvider = callable<[provider: ProviderInput], OkResult & { provider?: PublicProvider }>(
  "save_provider",
);
export const deleteProvider = callable<[providerId: string], OkResult>("delete_provider");
export const saveSettings = callable<
  [settings: { system_prompt: string; default_provider_id: string; default_model: string }],
  OkResult
>("save_settings");
export const newSession = callable<
  [],
  OkResult & { current_session_id?: string; messages?: AppState["messages"]; sessions?: SessionSummary[] }
>("new_session");
export const switchSession = callable<
  [sessionId: string],
  OkResult & { current_session_id?: string; messages?: AppState["messages"]; sessions?: SessionSummary[] }
>("switch_session");
export const clearSession = callable<
  [],
  OkResult & { current_session_id?: string; messages?: AppState["messages"]; sessions?: SessionSummary[] }
>("clear_session");
export const deleteSession = callable<
  [sessionId: string],
  OkResult & { current_session_id?: string; messages?: AppState["messages"]; sessions?: SessionSummary[] }
>("delete_session");
export const testProvider = callable<
  [providerId: string],
  OkResult & { message?: string; models?: string[]; vision_models?: string[] }
>("test_provider");
export const listModels = callable<[providerId: string], OkResult & { models?: string[]; vision_models?: string[] }>(
  "list_models",
);
export const sendMessage = callable<
  [providerId: string, model: string, content: string, requestId: string, aboutGame: string],
  OkResult & { messages?: AppState["messages"]; sessions?: SessionSummary[] }
>("send_message");
export const cancelChat = callable<[requestId: string], OkResult>("cancel_chat");
export const saveVoice = callable<[settings: Partial<VoiceSettings>], OkResult & { voice?: VoiceSettings }>("save_voice");
export const saveHearing = callable<[settings: Partial<HearingSettings>], OkResult & { hearing?: HearingSettings }>(
  "save_hearing",
);
export const pushToTalk = callable<[], OkResult & { hearing?: HearingSettings }>("push_to_talk");
export const stopListening = callable<[], OkResult & { hearing?: HearingSettings }>("stop_listening");
export const setHearingActivity = callable<
  [gameRunning: boolean, sleeping: boolean],
  OkResult & { hearing?: HearingSettings }
>("set_hearing_activity");
export const testVoice = callable<[], OkResult & { voice?: VoiceSettings; warning?: string }>("test_voice");
export const stopSpeaking = callable<[], OkResult>("stop_speaking");
export const retryKitten = callable<[], OkResult & { voice?: VoiceSettings }>("retry_kitten");
export const saveLastScreenshot = callable<[], OkResult & { path?: string }>("save_last_screenshot");
export const lookAtScreen = callable<
  [providerId: string, model: string, question: string, requestId: string, game: string, imageB64: string, qamHidden: boolean],
  OkResult & { messages?: AppState["messages"]; sessions?: SessionSummary[]; suggestions?: string[]; vision?: boolean }
>("look_at_screen");
export const startOAuth = callable<
  [providerId: string, flow: string],
  OkResult & { status?: string; message?: string; user_code?: string; verification_url?: string }
>("start_oauth");
export const cancelOAuth = callable<[providerId: string], OkResult>("cancel_oauth");
export const oauthStatus = callable<
  [providerId: string],
  OkResult & { status?: string; message?: string; user_code?: string; verification_url?: string }
>("oauth_status");
