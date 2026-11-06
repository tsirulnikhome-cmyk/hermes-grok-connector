"""The connector: one private MCP address per person, https://<public_host>/c/<key>/mcp.

Why a private address and not OAuth: Grok's custom-connector OAuth registered with a standard MCP authorization
server and then gave up before opening the sign-in page (see docs/lessons-learned.md). The unguessable key in the
address is the credential and decides whose agent and memory answer. In a Tesla, the car's Grok sign-in follows
the driver profile, so each driver reaches their own agent.

Six tools per person: my_context, ask_my_agent, send_to_backlog, remember, recall, forget. Most tell Grok to work
silently; send_to_backlog and a slow ask_my_agent tell it to say something back. Every result ends with STYLE, because
results reach Grok every time, unlike its saved tool list and the connector instructions.
The person's live briefing is also placed in the connector's instructions on every connection.
"""
from __future__ import annotations

import contextlib
import subprocess
import sys
import time

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .agent import AgentClient
from . import backlog as backlog_mod
from .config import Config, Person, resolve_secret
from .honcho_memory import memory_for
from .memory import MemoryError_

SILENT = (" Work silently: never say you are checking, asking or saving with the agent, connector or memory, and never"
          " mention them in the answer; just answer as if you knew.")
INSTRUCTIONS = ("This connector is the person's own assistant agent and memory. At the start of every conversation "
                "call my_context. It is the source of truth for {topics}, and for anything about them: use it instead "
                "of answering yourself or keeping your own notes. Use it silently; never mention the agent or "
                "connector to the person.")
CONTEXT_DOC = ("Answers \"what do you know about me\", \"who am I\", \"what's my day\". Call this FIRST, at the start of "
               "every conversation, before answering anything. Returns who the person is, their preferences and key "
               "people, today's items and what they recently asked you to remember. Use it silently to personalize "
               "your answers; don't read it aloud unless asked.")
ASK_DOC = ("Ask the person's own assistant agent. ALWAYS use this for {topics}. Pass the person's request in their "
           "own words with any needed context from this conversation. If the agent asks a question, read it to the "
           "person and pass their answer (for example 'yes') in the next call.")
ASK_REPLY = (" Always say something back. If the result says a request is still working, say that out loud, then call "
             "again with the same request to get the answer, unless it says not to.")
STYLE = ("\n\n(Speak this the way you'd tell a friend, in as few words as it takes. No closing line such as \"let me know\", "
         "\"anything else\" or \"enjoy your drive\". When a later request needs looking up, say two or three words like "
         "\"one sec\" before you call ask_my_agent, not the same ones each time.)")
BACKLOG_DOC = ("Save something to be followed up later at a computer, in a backlog file that the person or their coding "
               "assistants read. Use when they say send or pass this on, put this in the backlog or the questions file, "
               "have this checked later, or give feedback, a question or a bug to follow up. Use this instead of "
               "ask_my_agent for those: it saves at once and doesn't do the work. note: what they want, as close to "
               "their own words as you can. kind: bug | question | idea | concern. details: anything from this "
               "conversation needed to act on it, including what you told them yourself. Call it once for each thing, "
               "then always tell them out loud that it's saved and its number.")
REMEMBER_DOC = ("Save one lasting fact about the person in their own memory. Use when they say 'remember...', or tell "
                "you something that will still be true next week: a preference, a person in their life, a routine or "
                "schedule, a plan or date, a fact about their home or car. kind: preference | person | about (always "
                "loaded) or fact | plan | event (searchable notebook). Write one short self-contained sentence. If it "
                "changes something saved before, put a few words of the old item (or its id from recall) in "
                "`replaces` so the old one is updated instead of kept. Never save small "
                "talk, questions, one-time things, passwords, card or bank numbers, or the content of messages or "
                "emails. Before the conversation ends, save anything worth keeping that you haven't saved yet.")
RECALL_DOC = ("Search what the person told you before (their memory notebook). Use before saying you don't know "
              "something personal, and for 'what did I say about...' or 'what do you remember about...'.")
FORGET_DOC = ("Remove something from the person's memory when they ask you to forget it. Pass the item's id from "
              "recall, or a few words of it; if several match, read them out and ask which one.")


def _log(person: str, tool: str) -> None:
    print(f"TOOL {time.strftime('%Y-%m-%d %H:%M:%S')} {person} {tool}", file=sys.stderr, flush=True)


def extra_context(person: Person) -> list[str]:
    """Optional lines from the person's context_command (e.g. today's reminders), 10 s budget."""
    if not person.context_command:
        return []
    try:
        r = subprocess.run(person.context_command, capture_output=True, text=True, timeout=10)
        return [line for line in r.stdout.splitlines() if line.strip()][:12]
    except (OSError, subprocess.TimeoutExpired):
        return []


def person_server(person: Person, agent: AgentClient, backlog_file=None) -> MCPServer:
    mem = memory_for(person)
    s = MCPServer(name="home-agent", version="0.1.0", instructions=INSTRUCTIONS.format(topics=person.topics))

    @s.tool(description=CONTEXT_DOC + SILENT)
    def my_context() -> str:
        _log(person.id, "my_context")
        try:
            return mem.briefing(person.name, extra_context(person)) + STYLE
        except MemoryError_ as e:
            return str(e)

    @s.tool(description=ASK_DOC.format(topics=person.topics) + SILENT + ASK_REPLY)
    def ask_my_agent(request: str) -> str:
        _log(person.id, "ask_my_agent")
        return agent.ask_soon(person, request) + STYLE

    @s.tool(description=BACKLOG_DOC)
    def send_to_backlog(note: str, kind: str = "question", details: str = "") -> str:
        _log(person.id, "send_to_backlog")
        note = " ".join((note or "").split())
        if not note:
            return "Nothing was saved, because the note was empty. Ask the person what to save."
        recent = agent.recent_dialog(person)
        parts = ([f"From Grok:\n{details.strip()}"] if details.strip() else []) + \
                ([f"Through the agent:\n{recent}"] if recent else [])
        try:
            item = backlog_mod.add(backlog_file or agent.cfg.backlog_file, person.name, kind, note, "\n\n".join(parts))
        except OSError as e:
            print(f"backlog failed for {person.id}: {e!r}", file=sys.stderr, flush=True)
            return "That could not be saved to the backlog right now. Tell the person, and ask them to try again later."
        return f"Saved to the backlog as number {item['n']}. Say so to the person, in one short sentence."

    @s.tool(description=REMEMBER_DOC + SILENT)
    def remember(text: str, kind: str = "fact", replaces: str = "") -> str:
        _log(person.id, "remember")
        try:
            return mem.remember(text, kind, replaces)
        except MemoryError_ as e:
            return str(e)

    @s.tool(description=RECALL_DOC + SILENT)
    def recall(query: str) -> str:
        _log(person.id, "recall")
        try:
            return "\n".join(mem.recall(query)) or "Nothing saved about that."
        except MemoryError_ as e:
            return str(e)

    @s.tool(description=FORGET_DOC)
    def forget(item: str) -> str:
        _log(person.id, "forget")
        try:
            return mem.forget(item)
        except MemoryError_ as e:
            return str(e)

    return s


class _LiveInstructions:
    """ASGI wrapper: before each request, put the person's current briefing into the connector's instructions
    (sent to Grok when it connects). Rebuilt when the memory changes, and at least every minute for the clock and
    the extra lines."""

    def __init__(self, app, server: MCPServer, person: Person):
        self.app, self.server, self.person = app, server, person
        self.base = server._lowlevel_server.instructions
        self._at, self._ver, self._text = 0.0, None, ""

    def _text_now(self) -> str:
        mem = memory_for(self.person)
        try:
            ver = mem.version()
            if time.time() - self._at > 60 or ver != self._ver:
                brief = mem.briefing(self.person.name, extra_context(self.person))
                self._text = f"{self.base}\n\nWhat you already know about this person (from their memory):\n{brief}"
                self._at, self._ver = time.time(), ver
        except MemoryError_:      # a memory server that's down must not take the connector with it
            return self._text or self.base
        return self._text

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            import anyio
            self.server._lowlevel_server.instructions = await anyio.to_thread.run_sync(self._text_now)
        await self.app(scope, receive, send)


def build_app(cfg: Config):
    """The ASGI app: /c/<key>/mcp for each person; everything else is 404."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    sec = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                    allowed_hosts=[cfg.public_host, "127.0.0.1:*", "localhost:*", "testserver"],
                                    allowed_origins=[f"https://{cfg.public_host}"])
    agent = AgentClient(cfg)
    mounts, inner = [], []
    for person in cfg.people.values():
        key = resolve_secret(person.url_key)
        if len(key) < 24:
            raise SystemExit(f"{person.id}: the url_key secret is missing or shorter than 24 characters "
                             "(make one with: hermes-grok-connector new-key)")
        srv = person_server(person, agent)
        app = srv.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, transport_security=sec)
        inner.append(app)
        mounts.append(Mount(f"/c/{key}", app=_LiveInstructions(app, srv, person)))

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with contextlib.AsyncExitStack() as stack:
            for a in inner:
                await stack.enter_async_context(a.router.lifespan_context(a))
            yield

    return Starlette(routes=mounts, lifespan=lifespan)


def serve(cfg: Config) -> None:
    import uvicorn
    uvicorn.run(build_app(cfg), host=cfg.host, port=cfg.port, log_level="info")
