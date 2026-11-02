# Memory

## Two layers

The design follows what ChatGPT and agent frameworks such as Letta do: a small **core** memory that is always loaded,
and a larger **archival** store searched on demand.

| Layer | Holds | Loaded | Limit |
|---|---|---|---|
| **Profile** (`profile.json`) | `preference`, `person`, `about`: who they are, people in their life, standing preferences | at the start of every conversation (`my_context`, and the connector instructions) | 1,500 characters (~250 words); when full, the oldest item moves to the notebook, nothing is dropped |
| **Notebook** (`notes.json`) | `fact`, `plan`, `event`: everything else worth keeping | searched with `recall`; the 5 most recent appear in the briefing | 400 items; the least-used, oldest drop off |

Both are plain JSON in the person's folder, mode 0600. No AI model is involved in saving, searching or building the
briefing, so it is instant and free. Only `ask_my_agent` uses the agent (and its model).

## What gets saved

Grok calls `remember` when the person says "remember…" or shares something that will still be true next week:
preferences, people, routines and schedules, plans and dates, facts about their home and cars. The tool description
and the spoken instruction both list what **not** to save: small talk, questions, one-time things, passwords, card or
bank numbers, and message or email contents. The connector stores what it is given; the rule is enforced by the
instruction, so review the memory now and then.

## Updates, not duplicates

When something changes ("practice moved to Wednesdays"), Grok passes a few words of the old item (or its id from
`recall`) in `replaces`, and that item is updated. A near-identical repeat (90% of the same words) updates itself.
Word overlap alone never merges two different facts: "Dana's lesson is on Tuesdays" and "Sam's lesson is on Tuesdays"
stay separate.

## The briefing

```
Speaking with Alice. Now: Monday January 5, 2026 9:30 AM CST.
About them:
- Lives in Springfield; two kids, Dana (12) and Sam (9).
- Prefers aisle seats; likes the cabin at 70 degrees.
Today:                                   (optional context_command output)
- 17:00 call the plumber
Recently remembered:
- The lake cabin's new gate code was set in spring.
Use recall for anything else they may have told you before; save new lasting facts with remember.
```

## Seeding a starting profile

Starting empty works, but a short seeded profile makes the first conversations much better. Write 5–10 facts the
person approves:

```bash
hermes-grok-connector memory alice add about "Lives in Springfield; works as a nurse, night shifts Mon-Wed."
hermes-grok-connector memory alice add person "Husband Bob; kids Dana (12) and Sam (9)."
hermes-grok-connector memory alice add preference "Likes short, plain answers."
hermes-grok-connector memory alice briefing
```

Good sources: what the person's agent already knows, its existing memory notes, and their own list. Leave out money,
account numbers and anything from private messages.

## Viewing and editing

```bash
hermes-grok-connector memory alice show          # everything, with ids
hermes-grok-connector memory alice forget 3fa9   # by id, or by a few words
```

Or ask Grok: "What do you remember about me?", "Forget the gate code."

## Why not the agent's built-in memory?

Hermes has its own memory (`MEMORY.md` / `USER.md`), injected into every chat of that profile. If a profile serves
several people (for example a family iMessage line), personal notes would leak into everyone's chats. A separate
per-person store keeps the car memory private to its owner. If a profile serves exactly one person, you can still
point `memory_dir` at a folder the agent also exposes to that person through a small tool.

## Optional: Honcho instead of files

The file memory has no layer between the model and the raw text: it stores sentences, matches words ("car" won't find
"Tesla"), and only merges near-identical repeats. That's fine for a short list and gets worse as the list grows.
[Honcho](https://github.com/plastic-labs/honcho) (self-hosted, AGPL) is that missing layer: a worker turns
conversations into separate facts, keeps a short card per person, and searches by meaning. If the person's Hermes agent
uses Honcho too, the car and their chats share one memory.

Configure it per person; anyone without a `honcho:` block stays on files:

```yaml
honcho:
  base_url: http://127.0.0.1:8000
  workspace: family
  api_key: keychain:honcho/connector
people:
  alice:
    honcho: {observer: alice-agent, peer: alice}   # observer = the aiPeer in her agent's honcho.json
```

`hermes-grok-connector memory alice add …` works the same, which is also how to bring old notes across.

What we learned self-hosting it with Hermes (Honcho and the Hermes plugin change quickly, so check current docs):

- **Choose the embedding model carefully.** Its size is fixed for the life of the database; changing the model means
  wiping and re-importing. Local `bge-m3` through Ollama (1024 dimensions, many languages) ranked well for us.
  `qwen3-embedding` did not: it expects an instruction prefix on queries that Honcho doesn't add, so short generic facts
  came first for every question.
- **Non-default vector size:** run `scripts/configure_embeddings.py --yes` after migrations, or Honcho refuses to start.
- **Models need tool calling.** Honcho's own settings work with an Anthropic key; Claude Haiku is enough for the
  background worker.
- **The worker batches.** It waits for about a page of text or 30 minutes, so new facts don't appear at once.
- **Key in `honcho.json`.** For a local base URL, the Hermes plugin ignores `HONCHO_API_KEY` from `.env` and sends a
  placeholder. With auth on, put `apiKey` in the host block (chmod 600).
- **`hermes plugins enable honcho` can drop `memory.provider`.** Set it again afterwards and check `hermes memory status`.
- **Keep automation out of a person's memory.** One-shot runs have no sender id, so don't use `pinUserPeer` on a shared
  profile. Map real senders with `userPeerAliases` (phone numbers, and `api` for the car channel), set `peerName` to a
  holding peer, and set `observe_me: false` on it.
- **Agents with built-in notes:** the plugin mirrors only `user` writes, not `memory` ones. Tell the agent in its
  `SOUL.md` to save facts about the person with `honcho_conclude`.
