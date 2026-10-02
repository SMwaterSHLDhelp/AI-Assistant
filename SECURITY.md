# Security policy

## Supported versions

Security fixes go to the `main` branch and ship in the next GitHub Release of the plugin. Prereleases (tags that contain a hyphen, such as `v0.1.0-rc.3`) are test builds. There is no older stable branch.

## Reporting a vulnerability

Please report vulnerabilities privately. Do not open a public issue, and do not paste API keys, OAuth tokens, `credentials.json`, or session transcripts.

Use GitHub private vulnerability reporting:

https://github.com/SMwaterSHLDhelp/Deckling/security/advisories/new

That page works after a repository admin enables **Private vulnerability reporting** under Settings → Code security. If the page is unavailable, contact the repository owner through GitHub and describe the impact without including secrets. A maintainer will reply with a way to share the details.

## In scope

- How the plugin stores API keys and OAuth tokens (`credentials.json`, file modes).
- Secrets written to the Decky log, crash text, or the UI.
- The plugin sending a saved credential somewhere other than the provider URL the user configured.
- The optional Claude Code bridge on a LAN.

## Out of scope

- Behavior of OpenAI, Anthropic, xAI, Google, OpenRouter, or other providers.
- A provider URL the user typed in themselves. The plugin talks to that host on purpose.
- Decky Loader or SteamOS issues that are not caused by this plugin.
