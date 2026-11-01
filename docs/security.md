# Security and privacy

## The private address is the key

Each person's address is `https://<host>/c/<key>/mcp` with a random key of at least 24 characters. Anyone with the
address can talk to that person's agent (within the car tool limits) and read their connector memory. Treat it like
a password:

- store the key as a secret reference (`keychain:`, `env:`, `file:`); the config refuses plain values;
- share it only by pasting it into the person's own Grok account;
- **rotate** if it leaks: `hermes-grok-connector new-key`, store the new value, restart, re-add in Grok. The old
  address stops working immediately (404).

Unknown addresses and every other path return 404. There is no listing and no shared endpoint.

## Why not OAuth

MCP's standard is OAuth with dynamic client registration. Grok's custom connectors registered successfully with a
spec-compliant server and then failed with "Connection failed" before ever opening the sign-in page (November 2026).
Some public Grok OAuth templates also only "confirm authorization", without checking *who* signs in, so any Grok user
who completes them can call every tool. A per-person private address is simpler and ties identity to the address.
See [lessons-learned.md](lessons-learned.md).

## Driver profiles are identities

In the car, whoever selects your driver profile is signed in to Grok as you and reaches your agent. That's the same
trust you give someone you hand your unlocked phone to. Use [tool limits](tool-limits.md) to decide what the car
channel can do at all.

## What leaves your machine

- Everything Grok sends to the connector, and everything the connector returns (the answer, the briefing, memory
  items), passes through xAI's servers. Keep money, account numbers, passwords and message contents out of the car
  channel and out of memory.
- The connector itself sends nothing anywhere except to your agent's endpoint.

## Logs

The connector logs one line per tool call, `TOOL <time> <person> <tool>`, never arguments or answers. Uvicorn's access
log includes request paths, which contain the private keys: protect the log file (mode 600) or set
`log_level` to `warning` in your service if logs leave the machine.

## Reporting a problem

Please report security issues privately through GitHub's "Report a vulnerability" (Security tab), not in public
issues.
