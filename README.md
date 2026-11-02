# hermes-grok-connector

**Your own Hermes agent and lasting memory inside Grok and your Tesla: one private connector per driver, agent-first and silent.**

Grok in a Tesla (and in the Grok app) can use *custom connectors*. This project is a small connector server that gives
each person in the family:

- **their own agent**: Grok passes personal requests (reminders, tasks, your houses, your business, health benefits,
  whatever your agent knows) to that person's [Hermes](https://github.com/NousResearch/hermes-agent) agent and reads
  back the answer;
- **a lasting memory**: a short profile Grok gets at the start of every conversation, plus a notebook it searches when
  needed; "remember that I like the cabin at 70 degrees" is still known next week, in every car and in the app;
- **silent behavior**: Grok is told never to say "let me check with your agent"; it just answers.

```
 driver  ──voice──▶  Grok (car, signed in        ──MCP──▶  hermes-grok-connector  ──▶  that person's Hermes agent
                     per driver profile)                   /c/<private key>/mcp         (tools you allow for the car)
                                                                   │
                                                                   └──▶  that person's memory (profile + notebook)
```

In a Tesla, the car's Grok sign-in follows the **driver profile**, and each person adds their **own private connector
address** in their own Grok account. So whoever is driving reaches their own agent and memory, in any of the family's
cars. No sign-in step, no shared account.

> Status: working in daily use with Grok in Tesla Model S / 3 / X and the Grok iOS app (November 2026). Grok's
> connector behavior is changing fast; see [lessons learned](docs/lessons-learned.md).

## What you need

- A Hermes agent (one [profile](https://github.com/NousResearch/hermes-agent) per person, or one shared agent) with its
  **API server** turned on. Any agent that serves an OpenAI-style `POST /v1/responses` also works.
- A machine that runs the connector (macOS or Linux, Python 3.11+), usually the one running Hermes.
- A public HTTPS hostname that reaches it, e.g. a Cloudflare Tunnel. Grok's servers call it from the internet.
- A Grok account per person. Connectors work on free accounts; Grok Bot is **not** needed.
- Tesla: an AMD-processor car, software 2026.26 or later, Premium Connectivity or Wi-Fi.

## Quick start

```bash
git clone https://github.com/tsirulnikhome-cmyk/hermes-grok-connector
cd hermes-grok-connector
python3 -m venv .venv && .venv/bin/pip install -e .

mkdir -p ~/.hermes-grok-connector
cp examples/people.example.yaml ~/.hermes-grok-connector/people.yaml   # edit it

# one private key per person, stored as a secret (here: the macOS Keychain)
security add-generic-password -s hermes-grok-connector -a alice -w "$(.venv/bin/hermes-grok-connector new-key)"

.venv/bin/hermes-grok-connector serve                 # listens on 127.0.0.1:8797
.venv/bin/hermes-grok-connector url alice             # the address Alice pastes into Grok
```

Then, in each person's Grok app: **+ → Connectors → Add Connector → Custom**, paste their address, name it
**Home agent**, leave any login fields empty. Full steps: [docs/setup.md](docs/setup.md) and
[docs/grok-and-tesla.md](docs/grok-and-tesla.md).

## Making Grok use it first, silently

Grok decides on its own which connector to use, and it prefers its own memory for questions like "what do you know
about me". Two things fix that:

1. The connector's tool descriptions already say: call `my_context` first, use the agent for personal topics, work
   silently.
2. Each person says this once to Grok (in the car, under their own driver profile). Grok saves it in its own memory
   for that account, so it applies in every car they drive:

> "Grok, remember this for every conversation. Before you answer anything, silently check my Home agent connector
> first, and start every conversation by silently getting my context from it. Use it for my reminders and notes, …
> and anything about me. When I tell you something that will still be true next week, save it to Home agent without
> asking: my preferences, people in my life, routines and schedules, plans and dates, and facts about my home and
> cars. If something changes, update it instead of saving a duplicate. Don't save small talk, my questions, or
> one-time things, and never save passwords, card or bank numbers, or messages and emails. Never say you're checking
> or saving with the agent or connector, and never mention it. Just answer. If Home agent has nothing, use your own
> knowledge."

The full text and test phrases are in [docs/grok-and-tesla.md](docs/grok-and-tesla.md).

## The five tools

| Tool | Grok uses it | What it does | Cost |
|---|---|---|---|
| `my_context` | at the start of a conversation, "what do you know about me" | profile, recent notes, optional extra lines (e.g. today's reminders) | free, instant |
| `ask_my_agent` | personal requests: reminders, tasks, your topics | asks the person's agent, chains replies for the day so a spoken "yes" works | your agent's usual cost |
| `remember` | "remember…", lasting facts | saves to profile or notebook; a close match is updated, not duplicated | free |
| `recall` | "what did I say about…" | searches the notebook | free |
| `forget` | "forget…" | removes one item | free |

## Documentation

- [Setup](docs/setup.md): install, configuration, Hermes API server, Cloudflare Tunnel, run as a service
- [Grok and Tesla](docs/grok-and-tesla.md): adding the connector, driver profiles, the spoken instruction, tests
- [Memory](docs/memory.md): profile vs notebook, what is saved, limits, viewing and editing, optional Honcho backend
- [Car tool limits](docs/tool-limits.md): give the car channel only the agent tools you want (e.g. no email, no bank)
- [Security and privacy](docs/security.md)
- [Lessons learned](docs/lessons-learned.md): what we found out about Grok connectors the hard way
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT, © 2026 Yevgeni Tsirulnik. Not affiliated with Tesla, xAI / SpaceXAI or Nous Research.
