# Changelog

## 0.3.0 (2026-11-02)

- New tool `send_to_backlog`: the person says "pass this on" or "put this in the backlog", and it's saved at once to a
  JSON file with the recent conversation. Read it with `hermes-grok-connector backlog`, or from any coding assistant on
  the machine. See docs/backlog.md.
- `ask_my_agent` always answers within `wait_seconds` (default 20). A long job keeps running, its answer goes to the
  person's optional `notify_command` and is read out at the next request, and repeats while it runs aren't started.
  The default agent `timeout` is now 600, since nobody is waiting on the line.

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
