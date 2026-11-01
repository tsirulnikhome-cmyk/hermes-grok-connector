# Lessons learned

Things we found out building this with Grok in a family's Teslas (November 2026). Grok changes quickly, so some of
these may already be different.

## Grok's custom-connector OAuth gave up after registering

A standard MCP authorization server (protected-resource metadata, authorization-server metadata, dynamic client
registration, PKCE S256) was discovered correctly. Grok registered (`client_secret_post`, redirect
`https://grok.com/connectors-oauth-exchange-code/`) and then showed **"Connection failed"** without ever requesting
`/authorize`. A trailing slash in the `issuer` (`https://host/` vs `https://host`) was one real mismatch, but fixing
it did not help. Another developer reported the same symptom with nothing in their logs. **A connector address
without auth worked first time**, so this project uses a per-person private address.

## The car connects only when it decides to

Grok in the car opens the connection, reads the tool list and calls a tool **only for requests it decides belong to
the connector**. It does not connect at the start of a conversation. So the connector's instructions (even with the
person's briefing inside) are not seen for questions Grok answers on its own, like "what do you know about me".

## Grok prefers its own memory

Asked "what do you know about me?", the car answered from Grok's own memory of past car conversations (language,
habits with climate, music and navigation, the car model), and no tool was called. What fixed routing
was an instruction Grok saves in its own memory, spoken once per account: "before you answer anything, silently check
my Home agent connector first…". The full text is in [grok-and-tesla.md](grok-and-tesla.md).

## There is no "connector priority" setting

Which tool to use is decided by the model on every request. Tool descriptions, the connector instructions and the
person's instruction can only influence it. Saying "Home agent, …" always works.

## The Grok sign-in follows the Tesla driver profile

Switching driver profiles switched the car's Grok account. That makes per-person connectors work in shared cars: four
drivers and four cars, with each driver's own agent and memory in any car.

## Grok re-reads the tool list every conversation

Adding tools or changing descriptions needs no re-adding of the connector. Stateless HTTP serving fits this well.

## Silence must be asked for, twice

Without instructions, Grok narrates ("let me check with your agent…", "I checked your connector"). Saying "never
mention the agent or connector" in the spoken instruction **and** in every tool description stopped it.

## "Remember lasting things" is too vague

Spell out the categories (preferences, people, routines, plans, home and car facts) and the exclusions (small talk,
questions, one-time things, secrets, message contents).

## Word overlap is a bad way to spot updates

"X's practice is Tuesdays" vs "Y's practice is Tuesdays" share most words but are different facts. The `remember` tool
takes `replaces` (a few words of the old item) for real updates, and only near-identical repeats merge automatically.

## Cloudflare blocks Python's default user agent

Requests with `Python-urllib/*` got 403 at Cloudflare's edge (never reaching the connector); curl, httpx, Go and
browsers passed. Grok's requests pass. Only your own test scripts are affected.

## Connectors cost nothing extra on the Grok side

Custom connectors work on free Grok accounts. Grok Bot (a paid add-on) is not needed: the person's agent does the
work. Heavy use may hit a free account's usage limit sooner, because tool calls add text.
