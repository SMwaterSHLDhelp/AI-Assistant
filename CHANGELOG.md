# Changelog

All notable changes to Deckling are recorded here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Move items from **Unreleased** into a version section before tagging. The release workflow copies that section into the GitHub Release notes. A tag that contains a hyphen, such as `v0.1.0-rc.4`, is published as a prerelease and does not replace `/releases/latest/`.

## [Unreleased]

## [0.1.0-rc.4] - 2026-10-02

### Changed

- The plugin is Deckling. The Quick Access title, settings page, toasts, and logs use that name. The install zip and the folder inside it are `Deckling`. On first start, credentials and chats are copied from the old AI Assistant folders when the new files are missing.
- After a Dependabot minor or patch merge, the auto-merge workflow starts the build and CodeQL workflows on `main`.

### Added

- Spoken replies, off until enabled. Piper is the default engine and KittenTTS is the second. Each downloads its voice on first use into the plugin data directory. Speed, a per-engine voice picker, and a test button are in settings. Playback uses the Deck user's PipeWire session and stops when you send, stop, or start a new chat. If KittenTTS cannot install, Piper still works.
- Screen help. Phrases such as "how do I do this" and "what am I looking at", the **Look at my screen** button, and Steam + Y when the controller API exists, capture the game, hide the Quick Access Menu first, and send a JPEG of about 1280px to the selected vision model with the game's name. Text-only models are called out, with a switch to one that can see images. The answer is short and is spoken when voice replies are on. Screenshots are not stored unless you save them, and a setting turns capture off.
- Dependabot updates for npm, the CI Python tools, and GitHub Actions, with minor and patch updates grouped apart from majors.
- A weekly Actions run that rebuilds against the latest `@decky/ui`, `@decky/api`, and Decky CLI, and opens an issue if that build fails.
- CodeQL scanning for JavaScript/TypeScript and Python.
- Mocked contract tests for each chat provider's request and response format.
- Security policy, bug and feature issue forms, and this changelog.

## [0.1.0-rc.3] - 2026-10-02

### Fixed

- Add provider no longer waits on `get_state` to fill the type list. The types ship with the frontend. A failed settings load shows the backend error, including when the plugin is still starting.

### Added

- After a provider is saved, or its URL or key changes, the settings page and the Quick Access chat load that server's models into a button list. A text field and Refresh models stay available.

## [0.1.0-rc.2] - 2026-10-02

### Fixed

- Adding a provider on the Deck. The type choices are buttons on the settings page, because the Steam dropdown does not open reliably there.
- llama.cpp accepts a base URL with or without `/v1`, uses the only loaded model when the model field is blank, and reports loading, API-key, and connection failures in plain language.
- Streaming reads `reasoning_content` when a model sends that instead of `content`.

## [0.1.0-rc.1] - 2026-10-02

### Added

- Decky Loader plugin that chats from the Quick Access Menu with OpenAI, Anthropic, Claude Code subscriptions, xAI Grok, Gemini, Hermes, Ollama, llama.cpp, and custom OpenAI-compatible servers.
- Credentials stored on the Deck at mode `0600`, with secrets redacted from the plugin log.
- GitHub Actions builds `AI-Assistant.zip` and attaches it to version tags.
