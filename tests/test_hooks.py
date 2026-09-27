"""Tests for the orchestrator plugin's hook scripts.

Run with: python3 -m unittest discover -s tests
Each test runs a script as Claude Code would: JSON on stdin, decision on stdout.
"""

import json
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "orchestrator", "scripts")
HOME = os.path.expanduser("~")


def run_hook(script, payload, env=None):
    proc = subprocess.run(
        ["python3", os.path.join(SCRIPTS, script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=True,
    )
    if not proc.stdout.strip():
        return None
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    return out["permissionDecision"]


class ConfigGuardTest(unittest.TestCase):
    cwd = "/work/project"

    def guard(self, tool, tool_input, **extra):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
                   "tool_input": tool_input, "cwd": self.cwd, **extra}
        return run_hook("config_guard.py", payload, env={"CLAUDE_PROJECT_DIR": self.cwd})

    def bash(self, command, **extra):
        return self.guard("Bash", {"command": command}, **extra)

    def test_file_tools_denied_on_protected_paths(self):
        for path in [".claude/settings.json", ".claude/agents/x.md", "CLAUDE.md", "sub/CLAUDE.md",
                     "CLAUDE.local.md", "AGENTS.md", ".mcp.json", ".git/hooks/pre-commit", ".git/config",
                     ".orchestrator/.gitignore", f"{HOME}/.claude/settings.json",
                     "~/.claude/plugins/cache/x/agents/a.md", "~/.gitconfig", "src/../.claude/x",
                     ".claude/worktrees/wt/.claude/settings.json"]:
            for tool in ["Edit", "Write", "MultiEdit"]:
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(self.guard(tool, {"file_path": path}), "deny")
        self.assertEqual(self.guard("NotebookEdit", {"notebook_path": ".claude/n.ipynb"}), "deny")

    def test_file_tools_allowed_elsewhere(self):
        for path in ["src/main.py", "README.md", ".orchestrator/runs/r.org",
                     ".claude/worktrees/wt/src/main.py", "~/.claude/projects/p/memory/MEMORY.md",
                     "~/.claude/plans/plan.md", "docs/claude.md.txt", ".github/workflows/ci.yml"]:
            with self.subTest(path=path):
                self.assertIsNone(self.guard("Write", {"file_path": path}))

    def test_reads_are_not_checked(self):
        self.assertIsNone(self.guard("Read", {"file_path": ".claude/settings.json"}))

    def test_researcher_writes_only_below_orchestrator(self):
        self.assertIsNone(self.guard("Write", {"file_path": ".orchestrator/artifacts/r/n.org"},
                                     agent_type="orchestrator:researcher"))
        self.assertEqual(self.guard("Write", {"file_path": "src/x.py"},
                                    agent_type="orchestrator:researcher"), "deny")
        self.assertIsNone(self.guard("Write", {"file_path": "src/x.py"},
                                     agent_type="orchestrator:implementer"))

    def test_bash_writes_to_protected_paths_denied(self):
        for command in [
            "echo x > .claude/settings.json",
            "echo x >> CLAUDE.md",
            "cat new 1> .mcp.json",
            "printf x &> .git/hooks/pre-commit",
            "echo '{}' | tee .claude/settings.local.json",
            "tee -a ~/.claude/settings.json < x",
            "sed -i 's/a/b/' .claude/agents/planner.md",
            "sed -Ei.bak 's/a/b/' CLAUDE.md",
            "perl -pi -e 's/a/b/' .mcp.json",
            "cp /tmp/evil.json .claude/settings.json",
            "cp -r /tmp/agents ~/.claude/agents/",
            "mv .claude/settings.json /tmp/x",
            "rm -rf .claude",
            "rm .orchestrator/.gitignore",
            "ln -s /tmp/x .git/hooks/pre-commit",
            "chmod +x .git/hooks/post-checkout",
            "truncate -s0 CLAUDE.md",
            "echo x >> AGENTS.md",
            "dd if=/tmp/x of=.claude/settings.json",
            "rsync -a /tmp/cfg/ ~/.claude/",
            "git checkout -- .claude/settings.json",
            "python3 -c \"open('.claude/settings.json','w').write('{}')\"",
            "bash -c 'echo x > CLAUDE.md'",
            "cd /tmp && echo x > $HOME/.claude/settings.json",
            "sudo tee /root/.claude/settings.json",
            "FOO=1 cp x .mcp.json",
            "cat <<EOF > .claude/settings.json\n{}\nEOF",
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.bash(command), "deny")

    def test_bash_config_commands_denied(self):
        for command in ["claude plugin install x@y", "claude plugin marketplace add a/b",
                        "claude config set x y", "claude mcp add x -- y",
                        "git config user.email a@b", "git config --global core.editor vim",
                        "git -c core.hooksPath=/tmp/h commit -m x",
                        "ORCHESTRATOR_RUN_STATE=commit bash run-init.sh x",
                        "export ORCHESTRATOR_RUN_STATE=commit"]:
            with self.subTest(command=command):
                self.assertEqual(self.bash(command), "deny")

    def test_bash_harmless_commands_allowed(self):
        for command in [
            "ls -la", "git status", "git diff HEAD~1", "npm test 2>&1 | tail -20",
            "cat .claude/settings.json", "grep -r agent .claude/", "head CLAUDE.md",
            "sed -n '1,20p' .claude/agents/planner.md", "cp .claude/settings.json /tmp/backup.json",
            "echo ok > /tmp/out.txt", "python3 -c 'print(1)'", "git config --get user.email",
            "git config --list", "claude --version", "mkdir -p .orchestrator/runs",
            "bash /root/.claude/plugins/cache/agents-and-skills/orchestrator/0.1.0/scripts/run-init.sh demo",
            "make build > build.log 2>&1", "pytest -q > .orchestrator/artifacts/r/test.log",
            "echo 'the CLAUDE.md file' > notes.txt", "timeout 10 npm test",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))

    def test_malformed_input_fails_closed(self):
        proc = subprocess.run(["python3", os.path.join(SCRIPTS, "config_guard.py")],
                              input="not json", capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_unbalanced_quotes_still_checked(self):
        self.assertEqual(self.bash("echo 'x > .claude/settings.json"), "deny")


class CheckpointTest(unittest.TestCase):
    def check(self, command, mode="default"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/work",
                   "permission_mode": mode, "tool_input": {"command": command}}
        return run_hook("checkpoint.py", payload)

    def test_risky_commands_ask(self):
        for command in ["git push", "git push --force origin main", "git -C repo push",
                        "cd x && git push -u origin feat", "git reset --hard HEAD~1",
                        "git clean -fdx", "git checkout -- .", "git restore .", "git branch -D feat",
                        "git rebase main", "git stash drop", "git tag -d v1", "rm -rf build",
                        "rm -r dir", "sudo rm -R /tmp/x", "gh pr create --fill", "gh pr merge 3",
                        "gh release create v1", "gh api -X DELETE repos/a/b", "npm publish",
                        "cargo publish", "docker push img"]:
            with self.subTest(command=command):
                self.assertEqual(self.check(command), "ask")

    def test_safe_commands_pass(self):
        for command in ["git status", "git commit -m 'push it'", "git log --oneline",
                        "git checkout -b feat", "git checkout main", "git branch -d merged",
                        "rm file.txt", "rm -f file.txt", "gh pr view 3", "gh api repos/a/b",
                        "npm test", "echo 'git push'", "grep -r 'rm -rf' ."]:
            with self.subTest(command=command):
                self.assertIsNone(self.check(command))

    def test_no_prompt_modes_deny(self):
        for mode in ["bypassPermissions", "dontAsk"]:
            with self.subTest(mode=mode):
                self.assertEqual(self.check("git push", mode=mode), "deny")
        self.assertEqual(self.check("git push", mode="auto"), "ask")

    def test_other_tools_ignored(self):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "x"}, "permission_mode": "default"}
        self.assertIsNone(run_hook("checkpoint.py", payload))


class RunInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_init(self, slug="demo", mode=None):
        env = {k: v for k, v in os.environ.items() if k != "ORCHESTRATOR_RUN_STATE"}
        if mode:
            env["ORCHESTRATOR_RUN_STATE"] = mode
        return subprocess.run(["bash", os.path.join(SCRIPTS, "run-init.sh"), slug],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def gitignore(self):
        return os.path.join(self.repo, ".orchestrator", ".gitignore")

    def test_default_ignores_run_state(self):
        proc = self.run_init()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("run state: ignore", proc.stdout)
        with open(self.gitignore()) as fh:
            self.assertIn("*", fh.read().splitlines())
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo,
                                capture_output=True, text=True, check=True)
        self.assertEqual(status.stdout, "")

    def test_run_file_created_then_resumed(self):
        first = self.run_init()
        self.assertIn("created run", first.stdout)
        run_file = [line.split(None, 2)[2] for line in first.stdout.splitlines()
                    if line.startswith("run file:")][0]
        with open(run_file) as fh:
            self.assertIn("* Work packages", fh.read())
        self.assertIn("resumed run", self.run_init().stdout)

    def test_commit_mode_removes_managed_gitignore(self):
        self.run_init()
        proc = self.run_init(mode="commit")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(self.gitignore()))
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo,
                                capture_output=True, text=True, check=True)
        self.assertIn(".orchestrator/", status.stdout)

    def test_commit_mode_keeps_foreign_gitignore(self):
        os.makedirs(os.path.dirname(self.gitignore()))
        with open(self.gitignore(), "w") as fh:
            fh.write("artifacts/\n")
        proc = self.run_init(mode="commit")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("not created by the plugin", proc.stderr)
        self.assertTrue(os.path.exists(self.gitignore()))

    def test_invalid_input_rejected(self):
        self.assertEqual(self.run_init(slug="Bad Slug").returncode, 64)
        self.assertEqual(self.run_init(mode="sometimes").returncode, 64)


class SubagentLogTest(unittest.TestCase):
    def test_appends_record(self):
        with tempfile.TemporaryDirectory() as data:
            for event in ["SubagentStart", "SubagentStop"]:
                subprocess.run(["python3", os.path.join(SCRIPTS, "log_subagent.py")],
                               input=json.dumps({"hook_event_name": event, "session_id": "s",
                                                 "agent_id": "a1", "agent_type": "orchestrator:explorer"}),
                               text=True, env={**os.environ, "CLAUDE_PLUGIN_DATA": data}, check=True)
            with open(os.path.join(data, "subagents.jsonl")) as fh:
                records = [json.loads(line) for line in fh]
        self.assertEqual([r["event"] for r in records], ["SubagentStart", "SubagentStop"])
        self.assertEqual(records[0]["agent_type"], "orchestrator:explorer")

    def test_never_fails(self):
        proc = subprocess.run(["python3", os.path.join(SCRIPTS, "log_subagent.py")],
                              input="garbage", text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
