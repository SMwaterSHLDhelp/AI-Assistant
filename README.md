# AI Assistant

AI Assistant is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for Steam Deck. It lets you connect to an AI provider and chat from the Quick Access Menu while a game is running.

The frontend uses the current Decky libraries: `@decky/ui` (the package that replaced `decky-frontend-lib`) and `@decky/api`. The backend is Python (`main.py`) and follows the official plugin layout so the Decky CLI can build an installable zip.

## Screenshots

Screenshots from a Steam Deck are not in the repo yet. They will replace this placeholder.

| Quick Access chat | Provider settings |
| --- | --- |
| _Not captured yet. The panel has a provider and model picker, the conversation, a text field that opens the on-screen keyboard, Send, Stop, Ask about the current game, Copy, and Clear._ | _Not captured yet. The settings page adds and edits providers, tests the connection, and sets the default model._ |

## Install

This plugin is **not in the Decky plugin store yet**. Install the zip yourself with Decky's developer tools.

1. Install Decky Loader from [decky.xyz](https://decky.xyz) if you have not already.
2. Download `AI Assistant.zip` from a [GitHub Release](https://github.com/SMwaterSHLDhelp/AI-Assistant/releases) or from the artifact on a successful Actions run.
3. Copy the zip to your Deck (a USB drive, SSH, or the browser download folder all work).
4. In Game Mode, open the Quick Access Menu and the Decky icon.
5. Open the settings gear, then **Developer**.
6. Choose **Install Plugin from ZIP** and select `AI Assistant.zip`.
7. If the plugin does not show up, restart Decky from that same menu. It appears as **AI Assistant**.

You can also unzip it so this folder exists:

```text
~/homebrew/plugins/AI Assistant/
  plugin.json
  package.json
  main.py
  LICENSE
  README.md
  dist/index.js
  py_modules/
```

Restart Decky after copying the folder. The folder name inside the zip is `AI Assistant`, which is the name in `plugin.json`.

## Building from source

You need Node.js 20 or newer and [pnpm](https://pnpm.io) 9. The Decky builder image runs `pnpm i --frozen-lockfile` with pnpm 9, so keep the lockfile in that format. Python 3.11 or newer is enough for the tests; the Deck uses the Python that ships with Decky Loader, and this plugin stays in the standard library.

```bash
corepack enable
corepack prepare pnpm@9.15.9 --activate
pnpm install
pnpm run build          # frontend -> dist/index.js
pnpm run typecheck
pnpm run lint
python3 -m pip install ruff pytest
ruff check main.py py_modules tests
pytest
```

The installable zip is produced by the Decky CLI, which builds the frontend inside the official builder image (Docker or Podman):

```bash
# https://github.com/SteamDeckHomebrew/cli/releases
decky plugin build -o ./out
```

That writes `out/AI Assistant.zip`. GitHub Actions does this on every pull request and on tags. See [`.github/workflows/build.yml`](.github/workflows/build.yml).

`pnpm run build` alone is enough to refresh `dist/` while you are developing. Decky only loads the zip layout above, not the TypeScript sources.

## Provider setup

Add a provider from the Quick Access panel's **Provider settings** button. **Test connection** calls the provider's model-list endpoint and does not send a chat prompt. Pick a default provider and model on that page. The chat panel can override the model for the current session.

API keys and OAuth tokens are stored in Decky's plugin settings directory (`credentials.json`, mode `0600`). The file is not world-readable, and secrets are redacted before anything is written to the plugin log. Leave a key field blank while editing to keep the saved value.

### OpenAI / ChatGPT

**API key (supported path for third-party apps).** Create a key at [platform.openai.com](https://platform.openai.com/api-keys). The default base URL is `https://api.openai.com/v1`. That is the normal way to call GPT models from this plugin. You pay through the OpenAI API, not through a ChatGPT Plus subscription.

**OAuth.** OpenAI publishes a real device-code flow and an authorization-code + PKCE flow at `https://auth.openai.com`. Both are implemented:

- Device code: `POST /api/accounts/deviceauth/usercode`, then poll `/api/accounts/deviceauth/token`, then exchange at `/oauth/token`. The verification page is `https://auth.openai.com/codex/device`.
- PKCE: the browser is sent to `/api/accounts/authorize` and redirects to `http://127.0.0.1:8137/auth/callback`. Register that exact redirect URI on your OAuth client.

You must paste an OAuth **client ID** that OpenAI has registered for you. This plugin does **not** embed the Codex CLI's client ID and does not pretend to be Codex. OpenAI does not give arbitrary third-party apps a client that spends a ChatGPT Plus or Pro quota. A Sign in with ChatGPT token is often an identity token and may be rejected by `api.openai.com`. **Test connection** shows that error as-is. If you do not have your own client ID, use an API key.

### Anthropic Claude

API key only, from [console.anthropic.com](https://console.anthropic.com/). The default base URL is `https://api.anthropic.com`.

Anthropic does not offer OAuth for third-party apps that call the Claude API. The login used by Claude.ai and Claude Code is first-party. This plugin does not imitate that login. There is no OAuth button for Claude.

### Google Gemini

**API key (recommended).** Create one in [Google AI Studio](https://aistudio.google.com/apikey). The default base URL is `https://generativelanguage.googleapis.com/v1beta`. An API key is the smaller permission grant.

**OAuth, if you want it.** Google documents both a [limited-input device flow](https://developers.google.com/identity/protocols/oauth2/limited-input-device) and installed-app PKCE. This plugin implements both, using a client you create in Google Cloud:

1. Enable the Generative Language API on the project.
2. Create an OAuth client. Use **TVs and Limited Input devices** for the device-code button (that type has a client secret; paste both the client ID and the secret). Use a **Desktop** client for the PKCE button.
3. For PKCE, register the redirect URI `http://127.0.0.1:8138/`.

Google's own Gemini OAuth quickstart requests the `cloud-platform` scope because `generateContent` has no narrower public scope, plus `generative-language.retriever`. This plugin requests those same scopes. That is a broad Google Cloud scope. Prefer an API key unless you specifically need OAuth.

### Nous Hermes

Hermes is reached through an OpenAI-compatible endpoint. The default is OpenRouter:

- Base URL: `https://openrouter.ai/api/v1`
- API key from [openrouter.ai/keys](https://openrouter.ai/keys)
- Default model: `nousresearch/hermes-4-70b` (the model list prefers ids that contain `hermes`; `nousresearch/hermes-4-405b` is the larger option)

OpenRouter does not offer a third-party OAuth flow for this. Use the API key.

To point at another Hermes host (a local vLLM, llama.cpp, or another OpenAI-compatible server), change the base URL. The path must include `/v1` when that server uses the OpenAI layout (`.../v1/chat/completions`).

### Ollama

No account. Set the base URL to the daemon, on the Deck or on your LAN:

- This Deck: `http://127.0.0.1:11434`
- Another computer: `http://192.168.x.x:11434`

Models come from `GET /api/tags`. Chat uses `POST /api/chat` with streaming. An API key is optional and only needed if you put a proxy in front of Ollama. Install Ollama on the Deck or on a PC, run `ollama serve`, and `ollama pull` a model before testing.

### llama.cpp server

Run `llama-server` (or `server`) with the OpenAI-compatible router. The usual base URL is `http://127.0.0.1:8080/v1`. The plugin calls `GET /v1/models` and `POST /v1/chat/completions`. If you started the server with `--api-key`, put that key in the API key field. Otherwise leave the key blank.

### Custom OpenAI-compatible

Same protocol as llama.cpp and OpenRouter: a base URL ending in `/v1`, optional bearer token, `GET /models`, and streaming `POST /chat/completions`. Use this for vLLM, LM Studio's local server, or any other compatible endpoint.

## Using the chat

Open **AI Assistant** in the Quick Access Menu.

- Pick a provider and a model. You can type a model id if the server did not list it.
- The text field is a Steam `TextField`, so it opens the on-screen keyboard. Send is a button, so you do not need a physical keyboard.
- Replies stream in as the backend emits Decky events.
- **Ask about the current game** reads the running game's name from Steam (`Router.MainRunningApp`) and includes it in that message. The button stays disabled when nothing is running. An empty message with that button asks for a short spoiler-free tip.
- **Copy** uses Steam's clipboard when it is available.
- **Clear chat** deletes the current conversation on the Deck. **New chat** starts another one. Older conversations stay in the conversation picker (up to 30).
- Only one reply streams at a time. **Stop** cancels it.

Each request also includes the system prompt from settings, if you set one. The model sees the latest 40 messages.

## Privacy

- Chat text is sent only to the provider URL you configured. This plugin has no separate telemetry server.
- API keys, OAuth client secrets, access tokens, and refresh tokens live in `credentials.json` under Decky's settings directory for this plugin. The directory is mode `0700` and the file is mode `0600`.
- Conversations live in `sessions.json` under Decky's runtime data directory, also mode `0600`.
- Logs record the provider type, model id, and status. A log filter redacts bearer tokens, `sk-` keys, Google API keys, and similar strings. Authorization headers are not logged. OAuth callback URLs are not logged, because they contain one-time codes.
- Uninstalling the plugin deletes `credentials.json` and `sessions.json`.
- OpenRouter, OpenAI, Anthropic, and Google each keep their own logs of requests you send them. Ollama and llama.cpp stay on your network only when the base URL is local.
- Google OAuth, if you use it, asks for the broad `cloud-platform` scope described above.

## Project layout

```text
plugin.json          Decky metadata (name, author, api_version)
package.json         pnpm manifest
rollup.config.js     @decky/rollup preset
src/                 React + TypeScript Quick Access panel and settings page
main.py              Decky Plugin class
py_modules/ai_assistant/   provider implementations (packaged into the zip)
decky.pyi            Type stubs for the loader's `decky` module
```

To add a provider, add a `ProviderKind` in `py_modules/ai_assistant/catalog.py` and a list/stream function in `providers.py`. OAuth is only wired for providers that publish a real flow (`openai` and `google`).

## Not done yet

- Submission to the Decky plugin store.
- Screenshots taken on a Deck.
- Image or file attachments.
- More than one streaming reply at a time.
- A way to spend a ChatGPT Plus subscription. OpenAI does not offer that to third-party clients, and this plugin does not reuse the Codex client ID.
- Anthropic OAuth. They do not offer it to third-party apps.

## License

MIT. See [LICENSE](LICENSE).
