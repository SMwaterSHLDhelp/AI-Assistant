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

export interface AppState {
  catalog: ProviderKindInfo[];
  providers: PublicProvider[];
  default_provider_id: string;
  default_model: string;
  system_prompt: string;
  current_session_id: string;
  sessions: SessionSummary[];
  messages: ChatMessage[];
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
};

export interface OkResult {
  ok: boolean;
  error?: string;
}
