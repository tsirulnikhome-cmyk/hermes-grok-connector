# Car tool limits

Whatever reaches the car channel can be said out loud, and anyone in the car who selects your driver profile is
"you". So give the API-server channel only the tools you want there. Your chat channels (iMessage, Telegram…) keep
their full tools.

## The simple way: whole toolsets

In the profile's `config.yaml`:

```yaml
platform_toolsets:
  api_server: [memory, houses, hotels]   # only these toolsets on the API server channel
```

Without this line the API server gets Hermes' default toolset, **including terminal commands**.

## Per tool: "everything except email and bank"

Hermes filters an MCP server's tools with `tools.include` / `tools.exclude` (exact names or fnmatch globs), and MCP
tools are named `mcp_<server>_<tool>`. So a **copy** of a server under a new name, with a filter, gives the car
channel a narrower version while chats keep the original:

```yaml
mcp_servers:
  finance:                     # used by chat channels: everything
    command: /opt/tools/finance-mcp
  finance_car:                 # same server, car channel only
    command: /opt/tools/finance-mcp
    tools:
      include: [fin_bills, fin_benefits, fin_hsa]        # no accounts, transactions, investments
  mail_and_house:
    command: /opt/tools/house-mcp
  mail_and_house_car:
    command: /opt/tools/house-mcp
    tools:
      exclude: ["*email*", "*attachment*"]               # globs also catch future email tools

platform_toolsets:
  api_server: [memory, finance_car, mail_and_house_car]
```

Use `exclude` with globs when your rule is "everything except…", so a tool added later that matches (`*email*`)
stays out automatically. Use `include` when the rule is "only these".

`examples/hermes_tool_limits.py` applies a small policy file (`examples/tool-limits.example.yaml`) to Hermes
profiles this way, with a dry-run mode. Run it as the Hermes user, then restart the gateway.

## Check it

From the car (or `hermes-grok-connector ask`), ask for something you blocked: "read my latest email". The agent
should say it isn't available. In our setup:

- "Read my latest email": "Email isn't available from the car."
- "What's in my checking account?": "I can't see your checking balance from the car."
- "What's my HSA balance?": answered (allowed).

## Actions still need a yes

Limits decide *which* tools exist. Your agent's own rules (confirm before acting, approvals) still apply on the car
channel, and replies are chained for the day, so a spoken "yes" reaches the question.
