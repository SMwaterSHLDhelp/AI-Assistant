# Changelog

All notable changes to AI Assistant are recorded here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Move items from **Unreleased** into a version section before tagging. The release workflow copies that section into the GitHub Release notes. A tag that contains a hyphen, such as `v0.1.0-rc.3`, is published as a prerelease and does not replace `/releases/latest/`.

## [Unreleased]

### Added

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
