# Setup

This takes about 30 minutes for the first person and 5 minutes for each one after.

## 1. Turn on the Hermes API server

The connector talks to Hermes through its OpenAI-style API server. In the Hermes home of the agent
(`~/.hermes/.env`):

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_KEY=<a long random value>
```

**One agent per person (recommended):** give each person their own Hermes profile. With
`gateway.multiplex_profiles: true`, one listener serves every profile at `/p/<profile>/v1/...`, and each profile needs
its **own** `API_SERVER_KEY` in `~/.hermes/profiles/<profile>/.env` (a named profile without a key is unreachable).
The default profile keeps the unprefixed `/v1/...`.

**Limit what the car channel can do.** Without a limit, the API server channel gets Hermes' full toolset, including
terminal commands. Set `platform_toolsets.api_server` in each profile's `config.yaml` to the toolsets you want. See
[tool-limits.md](tool-limits.md) for a per-tool version (e.g. "everything except email and bank").

Restart the Hermes gateway, then check:

```bash
curl -s http://127.0.0.1:8642/v1/responses -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","input":"Say hello in five words."}'
```

## 2. Install the connector

```bash
git clone https://github.com/tsirulnikhome-cmyk/hermes-grok-connector
cd hermes-grok-connector
python3 -m venv .venv && .venv/bin/pip install -e .
```

## 3. Configure people

```bash
mkdir -p ~/.hermes-grok-connector
cp examples/people.example.yaml ~/.hermes-grok-connector/people.yaml
```

For each person:

- `url_key`: a reference to their private address key. Make one with `hermes-grok-connector new-key` and store it as
  a secret: macOS Keychain (`security add-generic-password -s hermes-grok-connector -a alice -w "<key>"`), an
  environment variable, or a `chmod 600` file. Create Keychain items **with the `security` command** as shown: an item
  created by another program makes `security` wait on a hidden approval prompt (the connector gives up after 15 s
  with a clear error).
- `agent.path` and `agent.api_key`: their Hermes profile's endpoint and key.
- `topics`: the things their agent handles, in plain words. Grok reads this to decide when to use the connector, so
  be specific ("the lake cabin bookings and guests" beats "business").
- `context_command` (optional): a command whose output is added to the start-of-conversation briefing, e.g. a script
  that prints today's reminders from your agent.

Test without Grok:

```bash
.venv/bin/hermes-grok-connector ask alice "What do I have today?"
.venv/bin/hermes-grok-connector memory alice briefing
```

## 4. Give it a public HTTPS address

Grok's servers call the connector from the internet. Any HTTPS reverse proxy works; a Cloudflare Tunnel needs no open
ports. In your tunnel's `config.yml`, before the catch-all rule:

```yaml
  - hostname: agent.example.com
    service: http://127.0.0.1:8797
```

then `cloudflared tunnel route dns <tunnel> agent.example.com` and restart cloudflared. Only `/c/<key>/mcp` answers;
everything else is 404.

Note: Cloudflare's bot protection blocks the default Python `urllib` user agent. Grok's own requests pass, but your
own test scripts may get a 403 from Cloudflare (not from the connector). Test with `curl`.

## 5. Run it as a service

macOS (LaunchAgent, runs as you): `examples/launchd/com.example.hermes-grok-connector.plist`.
Linux (systemd user service): `examples/systemd/hermes-grok-connector.service`.

The log shows one line per tool call (`TOOL <time> <person> <tool>`), never the content, which is handy for checking
what Grok actually did.

## 6. Connect Grok

Get each person's address with `hermes-grok-connector url <person>` and continue with
[grok-and-tesla.md](grok-and-tesla.md).

## Memory and the agent's own user

The memory folders are plain JSON files (0600). If the connector runs as a different OS user than Hermes, that is
fine: the connector only talks to Hermes over HTTP. If you want the agent itself to read the same memory (for
example in its chat channels), point `memory_dir` somewhere both can reach, or expose it through a small tool; see
[memory.md](memory.md).
