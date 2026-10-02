# AI Assistant

AI Assistant is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for Steam Deck. It lets you connect to an AI provider and chat from the Quick Access Menu while a game is running.

The frontend uses the current Decky libraries: `@decky/ui` (the package that replaced `decky-frontend-lib`) and `@decky/api`. The backend is Python (`main.py`) and follows the official plugin layout so the Decky CLI can build an installable zip.

## Screenshots

Screenshots from a Steam Deck are not in the repo yet. They will replace this placeholder.

| Quick Access chat | Provider settings |
| --- | --- |
| _Not captured yet. The panel has a provider and model picker, the conversation, Send, Stop, Ask about the current game, Look at my screen, Save screenshot, Copy, and Clear._ | _Not captured yet. The settings page adds providers, picks a model, and sets voice and screen capture._ |

## Install

This plugin is **not in the Decky plugin store yet**.

### Install Plugin from URL

This is the path Decky's **Install Plugin from URL** button expects. The release asset is always named `AI-Assistant.zip`, so this address keeps working after each stable release:

`https://github.com/SMwaterSHLDhelp/AI-Assistant/releases/latest/download/AI-Assistant.zip`

1. Install Decky Loader from [decky.xyz](https://decky.xyz) if you have not already.
2. In Game Mode, open the Quick Access Menu and the Decky icon.
3. Open the settings gear, then **Developer**.
4. Choose **Install Plugin from URL**.
5. Paste the address above and confirm.
6. If the plugin does not show up, restart Decky from that same menu. It appears as **AI Assistant**.

`/releases/latest/` is the newest GitHub Release that is not a prerelease. That link starts working when `v0.1.0` is published. A test build cut from a branch uses a prerelease tag, and its zip is the asset on that prerelease, not this `latest` URL.

The zip has one top-level folder, `AI Assistant` (the `name` in `plugin.json`). Inside it are `plugin.json`, `dist/index.js`, `main.py`, `package.json`, and `LICENSE`, plus the Python package and the README. Decky installs that folder under `~/homebrew/plugins/`.

### Install Plugin from ZIP

1. Download `AI-Assistant.zip` from a [GitHub Release](https://github.com/SMwaterSHLDhelp/AI-Assistant/releases) or from the artifact on a successful Actions run.
2. Copy the zip to your Deck (a USB drive, SSH, or the browser download folder all work).
3. Open the same **Developer** menu.
4. Choose **Install Plugin from ZIP** and select `AI-Assistant.zip`.
5. Restart Decky if the plugin does not appear.

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
python3 -m pip install -r requirements-dev.txt
ruff check main.py py_modules tests bridge scripts
pytest
```

The installable zip is produced by the Decky CLI, which builds the frontend inside the official builder image (Docker or Podman):

```bash
# https://github.com/SteamDeckHomebrew/cli/releases
decky plugin build -o ./out
```

That writes `out/AI Assistant.zip` (the Decky CLI uses the name from `plugin.json`). The GitHub Actions workflow renames that file to `AI-Assistant.zip` before uploading it, and on tags `v*` it attaches that exact filename to the GitHub Release. The release notes are the matching section of [CHANGELOG.md](CHANGELOG.md). A tag that contains a hyphen, such as `v0.1.0-rc.1`, is published as a prerelease so it does not replace `/releases/latest/`. See [`.github/workflows/build.yml`](.github/workflows/build.yml).

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

### Anthropic Claude (API key)

API key only, from [console.anthropic.com](https://console.anthropic.com/). The default base URL is `https://api.anthropic.com`. You pay per token.

Anthropic does not offer OAuth for third-party apps that call this API. The login used by Claude.ai and Claude Code is first-party. This provider does not imitate that login and has no OAuth button.

### Claude Code (subscription)

This is the path for a **Claude Pro, Max, Team, or Enterprise** subscription, the same login Claude Code uses. It does not use an Anthropic API key and it does not bill per token. The plugin runs the official `claude` CLI (`claude -p --output-format stream-json`, with `--model` and `--resume` for the conversation). It does **not** reimplement Anthropic's OAuth and it does not send the subscription token to a private API itself.

Use of this provider is subject to [Anthropic's terms for Claude Code](https://code.claude.com/docs/en/legal-and-compliance). Each person signs in with their own Claude account. The plugin does not bundle Claude Code and does not implement a Claude.ai login of its own: it runs the unmodified `claude` binary, and a subscription login can only do what that plan allows.

Model choices are the CLI aliases `sonnet`, `opus`, and `haiku`. You can also type a full model id if your CLI accepts it. Rate limits and usage limits from the subscription are shown in the chat as their own message, not as a generic failure.

**On the Deck.** Install Claude Code from the [official setup page](https://code.claude.com/docs/en/setup) (the native installer, or `npm install -g @anthropic-ai/claude-code`). Leave **Bridge URL** empty. Either:

- run `claude login` in a terminal on the Deck, or
- save the provider, then press **Sign in with setup-token**. The plugin runs `claude setup-token`, shows any URL or code the CLI prints, and stores the token it prints in `credentials.json` (mode `0600`). That token is passed to the CLI as `CLAUDE_CODE_OAUTH_TOKEN`. You can also paste a token from a computer where you already ran `claude setup-token`.

If `claude` is not on `PATH`, **Test connection** explains how to install it. Tools are disabled for these chats (`--tools ""`), so the CLI is used as a conversation, not as an agent that edits files on the Deck.

**On a PC, for Decks without Node.** From a clone of this repo, on the computer that has Claude Code installed and signed in:

```bash
export CLAUDE_BRIDGE_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 bridge/claude_bridge.py --host 0.0.0.0 --port 8765
```

Sign in on that PC with `claude login` or `claude setup-token` before chatting. In the plugin, set **Bridge URL** to `http://<that-pc-lan-ip>:8765` and put the same secret in **Bridge shared secret**. The script only wraps `claude -p` and checks the secret. It does not log the secret or the prompt. Keep it on your LAN.

The bridge is not inside the Decky zip. Copy `bridge/claude_bridge.py` from this repository.

### xAI Grok

xAI's official OpenAI-compatible API. The default base URL is `https://api.x.ai/v1`. Chat uses streaming `POST /v1/chat/completions`. **Test connection** calls `GET /v1/models`. The default model is `grok-4.7`. This plugin does not call grok.com or other unofficial endpoints.

**API key.** Create one in the [xAI console](https://console.x.ai/). That is the path that bills the API.

**Device-code sign-in (SuperGrok or X Premium+).** xAI publishes an OAuth authorization server at `https://auth.x.ai`. Its [OpenID discovery document](https://auth.x.ai/.well-known/openid-configuration) lists a device-code endpoint, the device-code grant, refresh tokens, and public clients (`token_endpoint_auth_methods_supported` includes `none`, so there is no client secret). The plugin uses that device flow with xAI's public Grok CLI client id, the same client [Hermes Agent](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/xai-grok-oauth.md) documents for its xAI Grok OAuth provider. Scopes are the published set `openid profile email offline_access grok-cli:access api:access`. Tokens are stored in `credentials.json` (mode `0600`) and refreshed with the refresh token.

Press **Sign in with device code**, open the page, and enter the code. No OAuth client id or secret is required from you.

xAI decides which subscriptions can call the API this way. Hermes has seen HTTP 403 for some SuperGrok tiers after a successful browser login. If that happens, use an API key instead. The chat error says so.

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

On the computer that has the GGUF (a PC on your LAN, or the Deck itself):

```bash
llama-server -m model.gguf --host 0.0.0.0 --port 8080
```

`--host 0.0.0.0` is what lets the Deck reach a server running on another machine. Port 8080 is llama.cpp's default. If the Deck cannot connect, allow inbound TCP 8080 on that PC's firewall (Windows Defender Firewall, ufw, or the router, depending on where the server runs).

In the plugin, either base URL works:

- `http://192.168.x.x:8080`
- `http://192.168.x.x:8080/v1`

Use `http://127.0.0.1:8080` when llama-server is running on the Deck. Leave the model blank when the server has a single GGUF loaded; the plugin uses the id from `GET /v1/models`. If several models are loaded, pick one. If you started the server with `--api-key`, put that same value in the API key field. Otherwise leave the key blank.

While the model is still loading, llama-server answers HTTP 503. The plugin tells you to wait and try the connection again. A server that is not running, or a firewall that drops the port, is reported as a connection failure rather than a raw system error.

### Custom OpenAI-compatible

Same protocol as llama.cpp and OpenRouter: a base URL ending in `/v1`, optional bearer token, `GET /models`, and streaming `POST /chat/completions`. Use this for vLLM, LM Studio's local server, or any other compatible endpoint.

## Using the chat

Open **AI Assistant** in the Quick Access Menu.

- Pick a provider, then pick a model from the list the server returns (Ollama `/api/tags`, OpenAI-compatible `/v1/models`, and the same list for xAI, Gemini, and the other backends). Saving a provider, or changing its URL or key and saving again, loads that list. **Refresh models** loads it again. You can still type a model id if the server did not list it.
- The text field is a Steam `TextField`, so it opens the on-screen keyboard. Send is a button, so you do not need a physical keyboard.
- Replies stream in as the backend emits Decky events.
- **Ask about the current game** reads the running game's name from Steam (`Router.MainRunningApp`) and includes it in that message. The button stays disabled when nothing is running. An empty message with that button asks for a short spoiler-free tip.
- **Copy** uses Steam's clipboard when it is available.
- **Clear chat** deletes the current conversation on the Deck. **New chat** starts another one. Older conversations stay in the conversation picker (up to 30).
- Only one reply streams at a time. **Stop** cancels it. **Stop** also stops a spoken reply.

Each request also includes the system prompt from settings, if you set one. The model sees the latest 40 messages.

## Voice replies

Spoken replies are off until you turn them on in settings. Two engines are available:

- **Piper** is the default. The first test or spoken reply downloads the Piper program and the voice you picked into Decky's data directory for this plugin. Nothing is added to the plugin zip. The English voices are Lessac, Amy, Ryan, Alan, and Jenny Dioco, all medium quality. Lessac is the default.
- **KittenTTS** is the second engine. It installs its wheel into a virtual environment in that same data directory and downloads the nano int8 model on first use. Voices are Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, and Leo. Jasper is the default. If SteamOS cannot create that environment or install the wheel, KittenTTS is disabled with the reason, and Piper keeps working. **Try KittenTTS again** repeats the install.

Each engine has its own voice buttons, a speed of 0.8, 1, 1.25, or 1.5, and **Test voice**. Audio is played through the Deck user's PipeWire or PulseAudio session (`XDG_RUNTIME_DIR` and `PULSE_SERVER`). Sending a message, starting a new chat, or pressing **Stop** / **Stop speaking** interrupts playback. A KittenTTS process that is still resident is closed after it has been idle, so the model is not kept in memory. Piper exits after each line, which releases its model too.

A speech failure does not fail the chat. The text reply still appears.

## Looking at the screen

Ask "how do I do this", "what am I looking at", "help me with this", or "what should I do here" (and a few close variants such as "look at my screen"). You can also press **Look at my screen**. On a Deck whose Steam client exposes controller registration, Steam + Y (guide + Y) does the same thing. If that API is missing, the button still works.

The panel closes the Quick Access Menu first so the overlay is not in the picture, waits a moment, and then tries Steam's screenshot functions (`SteamClient.Screenshots` and `SteamClient.GameSessions`). The backend then tries, in order:

1. gamescope's control socket (`screenshot <path>` on a `gamescope*` socket in `XDG_RUNTIME_DIR`)
2. a gamescope PipeWire video node (`pw-dump`, then one frame)
3. a new `gamescope*.png` or `steam*.png` file under `/tmp`

The picture is resized so the long edge is about 1280 pixels and compressed to JPEG. It is sent with your question and the running game's name to the provider you selected, as a vision input:

- OpenAI, xAI Grok, llama.cpp, and custom OpenAI-compatible servers get an `image_url` data URL
- Anthropic gets a base64 image block
- Gemini gets inline JPEG data
- Ollama gets an `images` array (llava, qwen-vl, and similar)

Models that can take an image are marked **sees the screen** in the model list. If the selected model is text-only, the plugin says so and offers models from that server that can see the screen. Claude Code on the Deck cannot take a screenshot from this plugin; switch to another provider for screen help.

The answer uses a short Jarvis-style prompt: a few spoken sentences, friendly, and specific to the game on screen. It does not use your normal system prompt and it does not resend the whole chat. When voice replies are on, that answer is spoken.

**Screen capture** in settings turns the feature off. Screenshots are sent only to the provider you chose. They are kept in memory for **Save screenshot** and are otherwise not written to disk. Saved copies go in the plugin data directory under `saved-screenshots/`. Temporary capture files under `/tmp` are removed. Steam's own screenshot folder is not deleted.

## Privacy

- Chat text is sent only to the provider URL you configured. This plugin has no separate telemetry server.
- A screen-help screenshot is sent only to that same provider, only when you ask about the screen, and only if screen capture is enabled. It is not written into `sessions.json`. It stays on disk only if you press **Save screenshot**.
- API keys, OAuth client secrets, access tokens, and refresh tokens live in `credentials.json` under Decky's settings directory for this plugin. The directory is mode `0700` and the file is mode `0600`.
- Conversations live in `sessions.json` under Decky's runtime data directory, also mode `0600`.
- Logs record the provider type, model id, and status. A log filter redacts bearer tokens, `sk-` keys, Google API keys, and similar strings. Authorization headers are not logged. OAuth callback URLs are not logged, because they contain one-time codes.
- Uninstalling the plugin deletes `credentials.json` and `sessions.json`.
- OpenRouter, OpenAI, Anthropic, xAI, and Google each keep their own logs of requests you send them. Ollama, llama.cpp, and the Claude Code bridge stay on your network only when the base URL is local. Claude Code on the Deck talks to Anthropic through the official CLI, under your Claude subscription.
- Google OAuth, if you use it, asks for the broad `cloud-platform` scope described above.

## Project layout

```text
plugin.json          Decky metadata (name, author, api_version)
package.json         pnpm manifest
rollup.config.js     @decky/rollup preset
src/                 React + TypeScript Quick Access panel and settings page
main.py              Decky Plugin class
py_modules/ai_assistant/   provider implementations (packaged into the zip)
bridge/claude_bridge.py    optional PC-side companion for Claude Code (not inside the Decky zip)
decky.pyi            Type stubs for the loader's `decky` module
```

To add a provider, add a `ProviderKind` in `py_modules/ai_assistant/catalog.py` and a list/stream function in `providers.py`. OAuth is only wired for providers that publish a real flow (`openai`, `google`, and xAI's device-code server). Claude Code sign-in shells out to `claude setup-token` instead of calling Anthropic.

## Keeping it working

[Dependabot](.github/dependabot.yml) opens a pull request every Monday for npm, the CI Python tools in `requirements-dev.txt`, and GitHub Actions. Minor and patch updates are grouped. Major updates are a separate pull request and are not merged automatically. The plugin and `bridge/claude_bridge.py` do not install Python packages on the Deck.

Every push and pull request, including those Dependabot opens, runs typecheck, lint, the Python tests, and the Decky zip build. A separate workflow squash-merges a Dependabot minor or patch pull request after that build passes. It uses `GITHUB_TOKEN`, does not check out the pull request, and leaves major updates for a person.

A weekly workflow installs the latest `@decky/ui`, `@decky/api`, and Decky CLI, then typechecks, tests, and builds the zip. If that fails, it opens an issue labeled `decky-api-drift`. The next passing run closes the issue. CodeQL scans the JavaScript, TypeScript, and Python on pushes to `main`, on pull requests other than Dependabot's, and once a week.

Before tagging a release, move the **Unreleased** notes in `CHANGELOG.md` under that version. Report vulnerabilities the way [SECURITY.md](SECURITY.md) describes, not in a public issue.

### Repository settings a maintainer still has to turn on

This repository's automation token cannot change security settings. An admin needs to enable these under the repository Settings:

- **Code security → Dependabot alerts** and **Dependabot security updates**. The weekly version updates come from `dependabot.yml`. Security updates are a separate switch, and enabling them returned "Resource not accessible by integration" from this environment.
- **Code security → Private vulnerability reporting**, so the link in `SECURITY.md` opens a private advisory.
- **Code security → Code scanning**, if the CodeQL workflow fails because scanning is not enabled. The workflow is the advanced setup.
- **Actions → General → Workflow permissions → Read and write permissions**, if the auto-merge or drift-issue job fails with a permissions error. Squash merges are already allowed. **Allow auto-merge** can stay off: the workflow merges after the checks pass, and it does not approve reviews. If branch protection later requires a review, a person has to approve before that merge can succeed.

## Not done yet

- Submission to the Decky plugin store.
- Screenshots taken on a Deck.
- General file attachments. Screen help sends one JPEG for that question and does not keep a gallery.
- More than one streaming reply at a time.
- A way to spend a ChatGPT Plus subscription. OpenAI does not offer that to third-party clients, and this plugin does not reuse the Codex client ID.
- Anthropic API OAuth. They do not offer it to third-party apps. A Claude subscription is available through the Claude Code CLI provider above, which is a different product from the per-token API.

## License

MIT. See [LICENSE](LICENSE).
