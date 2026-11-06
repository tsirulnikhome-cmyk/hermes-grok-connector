# The backlog, and never leaving Grok silent

## Passing things on from the car

Say "put this in the backlog", or "pass this on, have someone check these numbers". Grok calls `send_to_backlog`, which
saves right away and returns the item number for Grok to say back. It doesn't ask the agent or do the work. Each item
holds your note, what Grok adds from the conversation, and what recently went through your agent (up to 12 exchanges
from the last 2 hours; a restart of the connector clears those).

Read it from anywhere on the machine:

```bash
hermes-grok-connector backlog
```

```bash
hermes-grok-connector backlog show 3
```

```bash
hermes-grok-connector backlog close 3 "fixed the door note"
```

The file is `backlog_file` in the config (default `~/.hermes-grok-connector/backlog.json`, mode 600). To let a coding
assistant pick it up, add one line to its global instructions, for example "when I say check the car backlog, run
hermes-grok-connector backlog". Nothing is acted on automatically.

Items are stored as said, so treat the file as private. It isn't filtered, and it can hold anything your agent answered.

## Long requests

Grok doesn't wait long for a tool. When one stalls it tends to send the request again, reworded, and the person hears
nothing (see lessons-learned.md). So `ask_my_agent` always returns within `wait_seconds` (default 20):

- A normal answer comes straight back.
- A longer job keeps running, and Grok is told to say so out loud and call again, at most twice more. Each repeat waits
  up to `repeat_wait_seconds` for the job and collects the answer; it never starts a second one. This hasn't yet been
  confirmed in a car.
- A different request while it runs gets "still working" and isn't started.
- A late answer nobody collected is read out at the person's next request, and after 2 minutes is also passed on stdin
  to `notify_command` if set:

```yaml
people:
  alice:
    notify_command: ["/Users/alice/bin/text-me.sh"]
```
