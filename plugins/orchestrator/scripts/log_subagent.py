#!/usr/bin/env python3
"""SubagentStart/SubagentStop hook: append one JSON line per event.

Writes to $CLAUDE_PLUGIN_DATA/subagents.jsonl. Used to see how often each
agent runs and for how long. Never blocks and never fails the session.
"""

import json
import os
import sys
import time


def main():
    try:
        data = json.load(sys.stdin)
        base = os.environ.get("CLAUDE_PLUGIN_DATA")
        if not base:
            return 0
        os.makedirs(base, exist_ok=True)
        record = {
            "ts": round(time.time(), 3),
            "event": data.get("hook_event_name"),
            "session_id": data.get("session_id"),
            "agent_id": data.get("agent_id"),
            "agent_type": data.get("agent_type"),
        }
        with open(os.path.join(base, "subagents.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
