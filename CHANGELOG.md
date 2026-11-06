# Changelog

## 0.4.0 (2026-11-05)

- Speak first: a slow `ask_my_agent` now tells Grok to say so and call again, at most twice more, and the repeat collects
  the running job's answer instead of being refused. New `repeat_wait_seconds` (default 12). `wait_seconds` stays 20 by
  default; a lower value is being tried. **Not yet confirmed that car Grok really calls again**; if it doesn't, the answer
  still comes at the next request or through `notify_command`.
- `notify_command` now fires only if nobody collected the answer within 2 minutes.
- "Done" is checked: when the agent says it set, sent or locked something and no matching tool ran in that reply, the
  person hears that it can't be confirmed. `check_claims: false` turns it off. Matching is by tool name, so it's a hint.
- Car requests ask the agent for low reasoning effort (`reasoning_effort`, sent as Hermes `model_options`): a request that
  took 33-35 seconds took 19 in our test.
- Every `ask_my_agent` and `my_context` result carries a short speaking-style line, and the default voice instructions
  rule out IDs and long numbers.
- A `JOB` log line gives agent time, tools used and whether a claim was flagged.

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
