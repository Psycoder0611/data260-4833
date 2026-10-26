"""Offline tests for HW7 Part 6 (no model, only a temporary sandbox).

pytest test_hw7_files_offline.py -q
"""

import json

import pytest

from hw7 import file_agent, file_tools
from run_hw07_part6 import FILES, GATE_CASES, INSTRUCTION, order_ok


@pytest.fixture()
def sandbox(tmp_path):
    root = tmp_path / "course_sandbox"
    root.mkdir()
    file_tools.set_sandbox(root)
    for name, text in FILES.items():
        file_tools.write_file(name, text)
    return root


# --- the six tools ---------------------------------------------------------


def test_read_file_max_lines(sandbox):
    file_tools.write_file("long.txt", "\n".join(str(i) for i in range(50)))
    out = file_tools.read_file("long.txt", max_lines=3)["data"]
    assert out["text"] == "0\n1\n2" and out["truncated"] and out["total_lines"] == 50
    assert not file_tools.read_file("app.py")["data"]["truncated"]


def test_write_file_makes_folders_and_stays_in_sandbox(sandbox):
    assert file_tools.write_file("sub/dir/a.txt", "hi")["success"]
    assert (sandbox / "sub" / "dir" / "a.txt").read_text() == "hi"
    for bad in ("../outside.txt", "/tmp/outside.txt"):
        out = file_tools.write_file(bad, "x")
        assert not out["success"] and "outside the sandbox" in out["error"]
    assert not file_tools.read_file("../x")["success"]


def test_edit_file_returns_a_short_diff(sandbox):
    out = file_tools.edit_file("settings.py", "DEBUG = True", "DEBUG = False")
    assert out["success"]
    assert "-DEBUG = True" in out["data"]["diff"]
    assert "+DEBUG = False" in out["data"]["diff"]
    assert "DEBUG = False" in (sandbox / "settings.py").read_text()
    assert not file_tools.edit_file("settings.py", "nothing like this", "x")["success"]
    file_tools.write_file("twice.txt", "a a")
    assert not file_tools.edit_file("twice.txt", "a", "b")["success"]  # not unique


def test_glob_and_search_with_file_pattern(sandbox):
    file_tools.write_file("notes/todo.txt", "DEBUG later")
    files = file_tools.glob_files("**/*.py")["data"]["files"]
    assert files == ["app.py", "settings.py", "utils.py"]
    hits = file_tools.search_in_files("DEBUG", file_pattern="*.py")["data"]
    assert [h["file"] for h in hits["matches"]] == ["settings.py"]
    assert hits["matches"][0]["line"] == 1
    everything = file_tools.search_in_files("DEBUG")["data"]["count"]
    assert everything == 2  # the .txt file counts when no pattern is given
    assert not file_tools.search_in_files("(")["success"]


def test_bash_runs_in_the_sandbox_only_when_the_gate_allows(sandbox):
    ok = file_tools.bash("cat settings.py")
    assert ok["success"] and "DEBUG = True" in ok["data"]["output"]
    blocked = file_tools.bash("rm -rf settings.py")
    assert not blocked["success"] and "blocked" in blocked["error"]
    assert (sandbox / "settings.py").exists()


# --- the safety gate -------------------------------------------------------

SHOULD_BLOCK = [
    "rm -rf /tmp/x", "rm -r folder", "rm -fr folder", "rm -f -r folder",
    "rm --recursive folder", "find . -delete", "sudo ls", "su root",
    "chmod 777 a.py", "chown me a.py", "dd if=/dev/zero of=/dev/sda",
    "mkfs.ext4 /dev/sda1", "diskutil erase disk2", "echo hi > /etc/hosts",
    "cat a >> /usr/local/x", "ls && rm -rf *", "ls; sudo reboot",
    "cat a | sh", "ls $(rm x)", "find . -exec rm {} +", "echo hi > notes.txt",
    "curl http://example.com", "", "cat a.py\nrm a.py", "cat a.py &",
    "cat a.py\nrm -rf x",
]  # fmt: skip
SHOULD_ALLOW = [
    "ls", "ls -la", "pwd", "cat a.py", "head -n 3 a.py", "grep -n DEBUG a.py",
    "wc -l a.py", "echo hello", "date", "ls | grep py", "git status",
    "find . -name '*.py'",
]  # fmt: skip


def test_redirect_to_dev_null_is_not_destructive_but_still_needs_confirmation():
    assert file_tools.is_destructive("ls > /dev/null") is False
    assert file_tools.confirm_bash("ls > /dev/null")["allow"] is False


@pytest.mark.parametrize("command", SHOULD_BLOCK)
def test_gate_blocks_by_default(command):
    result = file_tools.confirm_bash(command)
    assert result["allow"] is False and result["reason"]


@pytest.mark.parametrize("command", SHOULD_ALLOW)
def test_gate_allows_safe_commands(command):
    assert file_tools.confirm_bash(command)["allow"] is True
    assert file_tools.is_destructive(command) is False


@pytest.mark.parametrize(
    "command",
    ["rm -rf x", "sudo ls", "chmod 700 f", "dd if=a of=/dev/sda",
     "mkfs.ext4 /dev/sda", "echo x > /etc/y"],
)  # fmt: skip
def test_destructive_is_independent_of_safe_prefixes(command):
    assert file_tools.is_destructive(command) is True
    # even a command that starts with an allowed word stays destructive
    assert file_tools.is_destructive("ls ; " + command) is True
    assert file_tools.confirm_bash("echo ok && " + command)["allow"] is False


def test_explicit_confirmation_lets_a_destructive_command_through():
    result = file_tools.confirm_bash("rm -rf x", auto_approve=True)
    assert result["allow"] is True and "confirmed" in result["reason"]


def test_the_ten_command_gate_cases(sandbox):
    assert len(GATE_CASES) == 10 and sum(ok for _, ok in GATE_CASES) == 5
    for command, should_pass in GATE_CASES:
        assert file_tools.confirm_bash(command)["allow"] is should_pass


# --- integration with a scripted model ------------------------------------


def scripted(calls):
    state = {"i": 0}

    def chat(messages, temperature=0.0, seed=0):
        step = calls[state["i"]]
        state["i"] += 1
        return {"content": json.dumps(step), "input_tokens": 0,
                "output_tokens": 0, "latency_ms": 0}  # fmt: skip

    return chat


def test_agent_follows_glob_search_read(sandbox):
    steps = [
        {"action": "tool", "tool": "glob_files", "inputs": {"pattern": "**/*.py"}},
        {"action": "tool", "tool": "search_in_files",
         "inputs": {"pattern": "DEBUG", "file_pattern": "*.py"}},
        {"action": "tool", "tool": "read_file", "inputs": {"path": "settings.py"}},
        {"action": "final",
         "answer": "settings.py:\nDEBUG = True\nLOG_LEVEL = \"info\""},
    ]  # fmt: skip
    run = file_agent.run_file_agent(INSTRUCTION, chat_fn=scripted(steps))
    assert run["stop_reason"] == "final_answer" and order_ok(run["calls"])
    assert "DEBUG = True" in run["answer"]


def test_agent_survives_a_bad_tool_name_and_bad_inputs(sandbox):
    steps = [
        {"action": "tool", "tool": "rm_everything", "inputs": {}},
        {"action": "tool", "tool": "read_file", "inputs": {"wrong": 1}},
        {"action": "final", "answer": "gave up"},
    ]
    run = file_agent.run_file_agent(INSTRUCTION, chat_fn=scripted(steps))
    assert run["stop_reason"] == "final_answer"
    assert run["calls"][0]["success"] is False  # the bad inputs were reported
