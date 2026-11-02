# Changelog

## 0.2.0 (2026-11-01)

- Optional Honcho memory backend, per person (`honcho:` in the config, docs/memory.md): organized facts, a card per
  person, search by meaning, and one memory shared with the person's Hermes agent. Plain files stay the default.
- The connector keeps working when the memory server is down: tools say so, and the briefing falls back.

## 0.1.0 (2026-11-01)

First public version.

- Per-person private connector addresses (`/c/<key>/mcp`) for Grok custom connectors (app and Tesla).
- Five tools: `my_context`, `ask_my_agent`, `remember`, `recall`, `forget`; all ask Grok to work silently.
- Lasting memory per person: always-loaded profile (capped) and a searchable notebook; updates via `replaces`.
- Live briefing inside the connector instructions.
- Hermes API server backend (`/v1/responses`, multi-profile `/p/<profile>/...`), replies chained for the day.
- Secrets as references only (`env:`, `keychain:`, `file:`).
- Example car-channel tool limits for Hermes profiles.
