# Troubleshooting

## "Connection failed" when adding the connector

- Open the address in a browser: `https://agent.example.com/c/<key>/mcp` should **not** be 404 (a 4xx about the
  request method or `Accept` header is fine; 404 means a wrong key or the connector isn't running).
- Make sure you left Grok's login / OAuth fields empty.
- Check the connector log for `POST /c/…/mcp` from Grok. No request at all → DNS, tunnel or firewall.
- 502 from Cloudflare → the connector isn't running or is restarting.

## Grok answers from its own memory

- Look at the connector log: no `TOOL … my_context` / `ask_my_agent` line means Grok never called it.
- Say the "agent first, silently" instruction again under that driver profile ([grok-and-tesla.md](grok-and-tesla.md)).
- Start with "Home agent, …" to force it.
- Make `topics` in the config more specific: Grok matches requests against it.

## Grok says "let me check with your agent"

Say the instruction again; it includes "never mention the agent or connector". The tool descriptions already ask for
silence.

## "Your agent isn't reachable right now"

The Hermes gateway is down or the API server isn't enabled for that profile. Check with the curl test in
[setup.md](setup.md). For a named profile, the request must use `/p/<profile>/v1/responses` and that profile's own
`API_SERVER_KEY`.

## "Your agent didn't answer (error 401)"

Wrong or missing `agent.api_key` for that person. With multi-profile routing, the default profile's key is rejected
on `/p/<profile>/…`.

## The agent says something "isn't available from the car"

That's your [tool limits](tool-limits.md) working. Add the tool to the car channel if you want it there.

## A spoken "yes" isn't understood

Replies are chained per person for the day (up to 6 hours) **inside the running connector**. A restart in between
loses the thread; repeat the request.

## Memory saved the wrong thing

`hermes-grok-connector memory <person> show`, then `forget <id>`. Or tell Grok "forget …".

## My own test script gets 403

Cloudflare blocks Python's default `urllib` user agent. Use curl or set a `User-Agent` header.

## "keychain item … needs approval"

The Keychain item was created by another program, so macOS wants to ask before `security` reads it, which never
works for a background service. Re-create it with `security add-generic-password -U -s <service> -a <account> -w`,
or switch that secret to `env:` / `file:`.
