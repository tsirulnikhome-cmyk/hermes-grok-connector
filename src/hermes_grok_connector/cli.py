"""hermes-grok-connector <command>

  serve                       run the connector (see docs/setup.md)
  new-key                     print a new random private-address key (store it as a secret, never in the config)
  url <person>                print the person's private connector address (to paste into Grok)
  ask <person> <text>         ask the person's agent through the same path Grok uses (a test)
  memory <person> show        print the person's memory
  memory <person> add <kind> <text>      kind: preference | person | about | fact | plan | event
  memory <person> forget <id-or-words>
  memory <person> briefing    print what Grok gets at the start of a conversation
  backlog [open|all]          list what people sent from the car
  backlog show <n>            one item in full, with the conversation saved with it
  backlog close <n> <note>    mark it done

Options: --config PATH (default: $HGC_CONFIG or ~/.hermes-grok-connector/people.yaml)
"""
from __future__ import annotations

import json
import os
import secrets
import sys

from . import backlog as backlog_mod
from . import config as config_mod
from .agent import AgentClient
from .honcho_memory import memory_for
from .memory import MemoryError_
from .server import extra_context, serve


def _backlog(cfg, args: list[str]) -> int:
    sub = args[0] if args else "open"
    if sub == "show" and len(args) == 2:
        print(backlog_mod.show(cfg.backlog_file, int(args[1])))
    elif sub == "close" and len(args) >= 3:
        print(backlog_mod.close(cfg.backlog_file, int(args[1]), " ".join(args[2:])))
    elif sub in ("open", "all"):
        for i in backlog_mod.items(cfg.backlog_file):
            if sub == "all" or i["status"] == "open":
                print(f"#{i['n']} [{i['type']}] {i['status']} {i['logged']} from {i['from']}: {i['note'][:200]}")
    else:
        print(__doc__)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = os.environ.get("HGC_CONFIG", "~/.hermes-grok-connector/people.yaml")
    if "--config" in args:
        i = args.index("--config")
        path = args[i + 1]
        del args[i:i + 2]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = args[0]
    if cmd == "new-key":
        print(secrets.token_urlsafe(24))
        return 0
    cfg = config_mod.load(path)
    if cmd == "serve":
        serve(cfg)
        return 0
    if cmd == "backlog":
        return _backlog(cfg, args[1:])
    if len(args) < 2 or args[1] not in cfg.people:
        print(f"unknown person; configured: {', '.join(cfg.people)}", file=sys.stderr)
        return 2
    person = cfg.people[args[1]]
    if cmd == "url":
        print(f"https://{cfg.public_host}/c/{config_mod.resolve_secret(person.url_key)}/mcp")
    elif cmd == "ask" and len(args) >= 3:
        print(AgentClient(cfg).ask(person, " ".join(args[2:])))
    elif cmd == "memory" and len(args) >= 3:
        mem, sub = memory_for(person), args[2]
        try:
            if sub == "show":
                print(json.dumps(mem.dump(), indent=1, ensure_ascii=False))
            elif sub == "add" and len(args) >= 5:
                print(mem.remember(" ".join(args[4:]), args[3]))
            elif sub == "forget" and len(args) >= 4:
                print(mem.forget(" ".join(args[3:])))
            elif sub == "briefing":
                print(mem.briefing(person.name, extra_context(person)))
            else:
                print(__doc__)
                return 2
        except MemoryError_ as e:
            print(e, file=sys.stderr)
            return 2
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
