"""Apply car-channel tool limits to Hermes profiles (see docs/tool-limits.md).

For each profile in the policy: copies of the allowed MCP servers named <server>_car with an include/exclude filter,
and platform_toolsets.api_server set to the built-ins plus those copies. Chat channels keep the original servers.
Run as the Hermes user (needs ruamel.yaml, which Hermes' own venv has), then restart the gateway:

  ~/.hermes/hermes-agent/venv/bin/python hermes_tool_limits.py tool-limits.yaml [--check]
"""
import copy
import datetime
import sys
from pathlib import Path

from ruamel.yaml import YAML


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    check = "--check" in sys.argv
    y = YAML()
    y.preserve_quotes, y.width = True, 4096
    policy = YAML(typ="safe").load(Path(sys.argv[1]).read_text())
    home = Path.home() / ".hermes"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    for name, rule in (policy.get("profiles") or {}).items():
        path = (home if name == "default" else home / "profiles" / name) / "config.yaml"
        cfg = y.load(path.read_text())
        servers = cfg.get("mcp_servers") or {}
        toolsets = list(rule.get("builtin") or [])
        for srv, f in (rule.get("servers") or {}).items():
            if srv not in servers:
                print(f"{name}: no MCP server '{srv}'", file=sys.stderr)
                return 1
            car = copy.deepcopy(servers[srv])
            car.pop("tools", None)
            tools = {k: list(f[k]) for k in ("include", "exclude") if f.get(k)}
            if tools:
                car["tools"] = tools
            if f.get("env"):
                car["env"] = {**(car.get("env") or {}), **f["env"]}
            servers[f"{srv}_car"] = car
            toolsets.append(f"{srv}_car")
        for stale in [n for n in servers if n.endswith("_car") and n not in toolsets]:
            del servers[stale]
        cfg["mcp_servers"] = servers
        cfg.setdefault("platform_toolsets", {})["api_server"] = toolsets
        print(f"{name}: car channel = {', '.join(toolsets)}")
        if not check:
            path.with_name(f"config.yaml.bak-car-{stamp}").write_text(path.read_text())
            with path.open("w") as fh:
                y.dump(cfg, fh)
    print("dry run only" if check else "applied; restart the Hermes gateway")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
