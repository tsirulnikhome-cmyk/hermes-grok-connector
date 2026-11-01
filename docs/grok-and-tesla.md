# Grok and Tesla

## Requirements

- **Grok:** a Grok account per person. Connectors, including custom ones, work on every plan, free included. Grok
  Bot is not needed: your agent does the work.
- **Tesla:** AMD infotainment processor (Controls → Software → Additional Vehicle Information), software 2026.26 or
  later for connectors, and Premium Connectivity or Wi-Fi.

## 1. Add the connector (each person, in their own Grok account)

In the Grok app: **+ → Connectors → Add Connector → Custom** (or on the web at grok.com/connectors → New Connector →
Custom).

- **URL:** the person's private address, `https://agent.example.com/c/<key>/mcp`
- **Name:** `Home agent` (use the same name for everyone so the spoken instruction is the same)
- Leave any login / OAuth / client ID fields **empty**.

Grok reconnects and re-reads the tool list for every conversation, so later changes to the connector need no
re-adding.

## 2. Sign the car's Grok in per driver

In the car: open Grok → **Sign In** and finish on the phone. Do this under each person's **driver profile**. In our
cars, switching the driver profile also switches the Grok sign-in, so each driver gets their own Grok account and
therefore their own connector and memory, in any car they drive.

Test it once: sign in under profile A, switch to profile B, and check Grok is signed out or shows B's account.

## 3. Tell Grok to use the agent first, silently

Grok has no setting to rank connectors. It decides per request, and for "what do you know about me" it prefers its
own memory. Grok in the car **only connects to a custom connector when it decides to use it**, so the connector cannot
inject anything before that. What works is an instruction Grok keeps in its own memory for that account.

With the person's driver profile selected, they say (replace the topics with theirs):

> "Grok, remember this for every conversation, and replace any earlier instructions about my Home agent. Before you
> answer anything, silently check my Home agent connector first, and start every conversation by silently getting my
> context from it. Use it for my reminders and notes, my houses and tenants, travel and hotels, bills, and health
> benefits and doctors, and anything about me. When I tell you something that will still be true next week, save it
> to Home agent without asking: my preferences, people in my life, routines and schedules, plans and dates, and facts
> about my home, cars and houses. If something changes, update it instead of saving a duplicate. Don't save small
> talk, my questions, or one-time things, and never save passwords, card or bank numbers, or messages and emails.
> Never say you're checking or saving with the agent or connector, and never mention it. Just answer. If Home agent
> has nothing, use your own knowledge."

Check it: *"What do you remember about how to answer me?"* Grok should repeat the rule.

Why spell out "lasting": a bare "save lasting things" is interpreted loosely. Grok then saves too little or saves
small talk. Concrete categories and exclusions work much better.

## 4. Test phrases

| Say | Expected |
|---|---|
| "What do you know about me?" | Answers from the profile (family, work, preferences) |
| "What reminders do I have?" | Agent answers, no "let me check" |
| "Remind me tomorrow at 9 to call the plumber." | Agent repeats it and asks for a yes; "yes" sets it |
| "I like the cabin at 70 degrees." | Saved without asking |
| New conversation: "What temperature do I like?" | "70" |
| "Navigate home", "play jazz" | Grok does it itself (car controls are Grok's, not the agent's) |
| Something your car limits block, e.g. "read my email" | Agent says it isn't available from the car |

Watch the connector log while testing: `TOOL ... my_context`, `ask_my_agent`, `remember` lines show what Grok
actually called. An answer with no matching log line came from Grok's own memory.

## If Grok still answers on its own

- Start with **"Home agent, …"**: that always routes to the connector.
- Say the instruction again. Users report that Grok's own memory occasionally stops loading; your agent's memory is
  separate and never lost.
- Check the Grok app for a setting to turn Grok's own memory off for that account; with nothing of its own to fall
  back on, it relies on the connector.
