"""测试入口只使用临时进程验证状态和诊断，不运行产品服务。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_tests
from scripts.run_tests import run


@pytest.mark.parametrize("exit_code", [0, 7])
def test_runner_keeps_command_exit_and_live_output(tmp_path: Path, exit_code: int) -> None:
    output = tmp_path / "result"
    command = [sys.executable, "-u", "-c", f"print('case-id'); raise SystemExit({exit_code})"]
    assert run(command, tmp_path, output, 10) == exit_code
    metadata = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert metadata["status"] == ("PASSED" if exit_code == 0 else "FAILED")
    assert metadata["exit_code"] == exit_code and metadata["command"] == command
    assert metadata["elapsed_seconds"] >= 0 and metadata["finished_at"]
    assert metadata["commit"] and metadata["dirty_worktree"] in (True, False)
    assert "case-id" in (output / "tests.log").read_text(encoding="utf-8")


def test_runner_timeout_keeps_diagnostics_and_stops_its_child(tmp_path: Path) -> None:
    output = tmp_path / "timeout"
    child = [sys.executable, "-u", "-c", "import time; print('hanging-child'); time.sleep(60)"]
    script = (
        "import subprocess, time; "
        f"child=subprocess.Popen({child!r}); "
        "print(child.pid, flush=True); time.sleep(60)"
    )
    assert run([sys.executable, "-u", "-c", script], tmp_path, output, 2) == 124
    metadata = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "TIMED_OUT" and metadata["exit_code"] != 0
    lines = (output / "tests.log").read_text(encoding="utf-8").splitlines()
    assert "hanging-child" in lines
    if sys.platform == "win32":
        pid = next(line for line in lines if line.isdigit())
        listing = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"])
        assert f'"{pid}"'.encode() not in listing


def test_runner_start_failure_is_not_a_test_failure(tmp_path: Path) -> None:
    output = tmp_path / "missing"
    assert run([str(tmp_path / "missing-command")], tmp_path, output, 10) == 1
    metadata = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "START_FAILED" and metadata["exit_code"] is None


def test_slow_test_dumps_stack_without_becoming_a_failure(tmp_path: Path) -> None:
    fixture = tmp_path / "test_slow_fixture.py"
    fixture.write_text("import time\ndef test_slow():\n    time.sleep(0.4)\n", encoding="utf-8")
    output = tmp_path / "stack"
    command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "-vv",
        "-o",
        "faulthandler_timeout=0.1",
        str(fixture),
    ]
    assert run(command, tmp_path, output, 30) == 0
    log = (output / "tests.log").read_text(encoding="utf-8")
    assert "Timeout" in log and "test_slow_fixture.py" in log and "PASSED" in log


def test_all_runs_sequentially_and_keeps_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def execute(command: list[str], cwd: Path, output: Path, timeout: float) -> int:
        commands.append(command)
        return 7 if len(commands) == 1 else 0

    def find_pnpm(name: str) -> str:
        return "pnpm"

    monkeypatch.setattr(sys, "argv", ["run_tests", "all"])
    monkeypatch.setattr(run_tests.shutil, "which", find_pnpm)
    monkeypatch.setattr(run_tests, "run", execute)
    assert run_tests.main() == 7
    assert len(commands) == 2 and "--maxWorkers=1" in commands[0]
    assert "pytest" in commands[1] and "faulthandler_timeout=120" in commands[1]


@pytest.mark.parametrize(
    "argv", [["all", "test.py"], ["frontend", "test&command"], ["backend", "--timeout", "nan"]]
)
def test_runner_rejects_changed_conditions(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_tests", *argv])
    with pytest.raises(SystemExit) as error:
        run_tests.main()
    assert error.value.code == 2
