"""Configuration: one YAML file (see examples/people.example.yaml). Secrets are references, never values:
  env:VAR_NAME                 an environment variable
  keychain:service/account     the macOS login Keychain (security find-generic-password)
  file:/path/to/file           the first line of a file (keep it chmod 600)
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_TOPICS = "their tasks and reminders, notes, plans, and anything their agent knows about"


class ConfigError(ValueError):
    pass


def resolve_secret(ref: str | None) -> str:
    """Turn a secret reference into its value. Plain values are refused so secrets never sit in the config."""
    if not ref:
        return ""
    kind, _, rest = str(ref).partition(":")
    if kind == "env":
        return os.environ.get(rest, "")
    if kind == "keychain":
        service, _, account = rest.partition("/")
        args = ["security", "find-generic-password", "-s", service, "-w"] + (["-a", account] if account else [])
        try:  # an item created by another program makes `security` wait on a GUI prompt; don't hang forever
            r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise ConfigError(f"keychain item {rest!r} needs approval: create it with `security add-generic-password` "
                              "(see docs/setup.md) or use env:/file:") from None
        return r.stdout.strip() if r.returncode == 0 else ""
    if kind == "file":
        p = Path(rest).expanduser()
        return p.read_text().splitlines()[0].strip() if p.exists() else ""
    raise ConfigError("secrets must be references (env:, keychain: or file:), not values")


@dataclass
class Agent:
    base_url: str = "http://127.0.0.1:8642"
    path: str = "/v1/responses"          # Hermes multi-profile: /p/<profile>/v1/responses
    api_key: str = ""                     # secret reference
    model: str = "hermes-agent"
    timeout: int = 600                    # the job itself; the person hears something after wait_seconds anyway
    wait_seconds: int = 20                # then ask_my_agent says "still working" and the job keeps running
    session_key: str = ""                 # X-Hermes-Session-Key, keeps one conversation thread per person


@dataclass
class HonchoServer:
    base_url: str = "http://127.0.0.1:8000"
    workspace: str = "hermes"
    api_key: str = ""                     # secret reference; empty when the server runs without auth


@dataclass
class HonchoPeer:
    server: HonchoServer
    observer: str                         # the AI peer; use the agent's aiPeer to share one memory with it
    peer: str                             # the person's peer


@dataclass
class Person:
    id: str
    name: str
    url_key: str                          # secret reference for the private connector address
    agent: Agent
    memory_dir: Path
    topics: str = DEFAULT_TOPICS
    context_command: list[str] = field(default_factory=list)  # extra briefing lines, e.g. today's reminders
    honcho: HonchoPeer | None = None      # optional: keep this person's memory in Honcho instead of files
    notify_command: list[str] = field(default_factory=list)  # gets a late answer on stdin, e.g. a script that texts it


@dataclass
class Config:
    public_host: str
    host: str
    port: int
    people: dict[str, Person]
    voice: str
    backlog_file: Path = Path("~/.hermes-grok-connector/backlog.json").expanduser()


VOICE = ("{name} is talking to you by voice through Grok, often while driving. Answer in one to three short spoken "
         "sentences: no lists, links, tables, emoji or markdown. Before anything that changes something, say exactly "
         "what you will do and ask for a yes; a 'yes' may arrive as the next message. If a tool you would need is not "
         "available here, say it isn't available from the car.")


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).expanduser().read_text()) or {}
    server = raw.get("server") or {}
    defaults = raw.get("agent_defaults") or {}
    memory_root = Path(raw.get("memory_root", "~/.hermes-grok-connector/memory")).expanduser()
    honcho = HonchoServer(**raw["honcho"]) if raw.get("honcho") else None
    people = {}
    for pid, p in (raw.get("people") or {}).items():
        if not re.fullmatch(r"[a-z0-9_-]+", pid):
            raise ConfigError(f"person id {pid!r}: use lowercase letters, digits, - or _")
        if not p.get("url_key"):
            raise ConfigError(f"person {pid}: url_key (a secret reference) is required")
        agent = Agent(**{**defaults, **(p.get("agent") or {})})
        agent.session_key = agent.session_key or f"grok-{pid}"
        cmd = p.get("context_command") or []
        notify = p.get("notify_command") or []
        peer = None
        if p.get("honcho"):
            if not honcho:
                raise ConfigError(f"person {pid}: has a honcho block, but there is no top-level honcho: section")
            hp = p["honcho"] if isinstance(p["honcho"], dict) else {}
            peer = HonchoPeer(honcho, observer=hp.get("observer", f"{pid}-agent"), peer=hp.get("peer", pid))
        people[pid] = Person(id=pid, name=p.get("name", pid.title()), url_key=p["url_key"], agent=agent,
                             memory_dir=Path(p.get("memory_dir", memory_root / pid)).expanduser(),
                             topics=p.get("topics", DEFAULT_TOPICS),
                             context_command=cmd if isinstance(cmd, list) else str(cmd).split(), honcho=peer,
                             notify_command=notify if isinstance(notify, list) else str(notify).split())
    if not people:
        raise ConfigError("no people configured")
    if not server.get("public_host"):
        raise ConfigError("server.public_host is required (the hostname Grok reaches, e.g. agent.example.com)")
    return Config(public_host=server["public_host"], host=server.get("host", "127.0.0.1"),
                  port=int(server.get("port", 8797)), people=people, voice=raw.get("voice_instructions", VOICE),
                  backlog_file=Path(raw.get("backlog_file", "~/.hermes-grok-connector/backlog.json")).expanduser())
