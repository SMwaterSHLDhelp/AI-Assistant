export interface ProviderKindInfo {
  kind: string;
  label: string;
  description: string;
  default_base_url: string;
  default_model: string;
  auth: string;
  oauth: string;
}

export interface PublicProvider {
  id: string;
  kind: string;
  name: string;
  base_url: string;
  default_model: string;
  max_tokens: number;
  has_api_key: boolean;
  api_key_last4: string;
  oauth_client_id: string;
  has_oauth_secret: boolean;
  oauth_connected: boolean;
  oauth_expires_at: number;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  created_at: number;
}

export interface SessionSummary {
  id: string;
  title: string;
  updated_at: number;
}

export interface VoiceSettings {
  voice_enabled: boolean;
  voice_engine: string;
  piper_voice: string;
  kitten_voice: string;
  voice_speed: number;
  screen_capture: boolean;
  kitten_error: string;
  piper_voices: string[];
  kitten_voices: string[];
}

export function defaultVoice(): VoiceSettings {
  return {
    voice_enabled: false,
    voice_engine: "piper",
    piper_voice: "en_US-lessac-medium",
    kitten_voice: "Jasper",
    voice_speed: 1,
    screen_capture: true,
    kitten_error: "",
    piper_voices: [
      "en_US-lessac-medium",
      "en_US-amy-medium",
      "en_US-ryan-medium",
      "en_GB-alan-medium",
      "en_GB-jenny_dioco-medium",
    ],
    kitten_voices: ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"],
  };
}

export interface AppState {
  catalog: ProviderKindInfo[];
  providers: PublicProvider[];
  default_provider_id: string;
  default_model: string;
  system_prompt: string;
  current_session_id: string;
  sessions: SessionSummary[];
  messages: ChatMessage[];
  voice: VoiceSettings;
}

export interface ProviderInput {
  id?: string;
  kind: string;
  name: string;
  base_url: string;
  default_model: string;
  max_tokens: number;
  api_key: string | null;
  oauth_client_id: string;
  oauth_client_secret: string | null;
}

export type BackendEvent = {
  type: string;
  request_id?: string;
  session_id?: string;
  text?: string;
  error?: string;
  cancelled?: boolean;
  messages?: ChatMessage[];
  sessions?: SessionSummary[];
  provider_id?: string;
  status?: string;
  message?: string;
  user_code?: string;
  verification_url?: string;
  flow?: string;
  suggestions?: string[];
  vision?: boolean;
};

export interface OkResult {
  ok: boolean;
  error?: string;
}
