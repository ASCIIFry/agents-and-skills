#!/usr/bin/env python3
"""Summarise the orchestrator plugin's subagent log.

Usage: tools/subagent-stats.py [path/to/subagents.jsonl]
Default path: ~/.claude/plugins/data/orchestrator-agents-and-skills/subagents.jsonl
Prints runs and total/median duration per agent type.
"""

import json
import os
import statistics
import sys
from collections import defaultdict

DEFAULT = "~/.claude/plugins/data/orchestrator-agents-and-skills/subagents.jsonl"


def main():
    path = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    starts, durations, unfinished = {}, defaultdict(list), defaultdict(int)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            key = (rec.get("session_id"), rec.get("agent_id"))
            if rec.get("event") == "SubagentStart":
                starts[key] = rec
            elif rec.get("event") == "SubagentStop" and key in starts:
                start = starts.pop(key)
                durations[start.get("agent_type") or "?"].append(rec["ts"] - start["ts"])
    for start in starts.values():
        unfinished[start.get("agent_type") or "?"] += 1

    print(f"{'agent':<28}{'runs':>6}{'total min':>11}{'median s':>10}{'open':>6}")
    for agent in sorted(set(durations) | set(unfinished)):
        d = durations.get(agent, [])
        total = sum(d) / 60
        median = statistics.median(d) if d else 0
        print(f"{agent:<28}{len(d):>6}{total:>11.1f}{median:>10.0f}{unfinished.get(agent, 0):>6}")


if __name__ == "__main__":
    main()
