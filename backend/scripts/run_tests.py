"""本地与 CI 共用测试参数，保留日志和明确的结束状态。"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import BinaryIO, cast
from uuid import uuid4

from filelock import FileLock, Timeout

ROOT = Path(__file__).resolve().parents[2]


def lock_path() -> Path:
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, text=True
    ).strip()
    return Path(common) / "knowrealm-tests.lock"


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def run(command: list[str], cwd: Path, output: Path, timeout: float) -> int:
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "command": command,
        "cwd": str(cwd),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        "dirty_worktree": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
            )
        ),
        "started_at": datetime.now(UTC).isoformat(),
        "timeout_seconds": timeout,
        "status": "RUNNING",
        "exit_code": None,
    }
    record = output / "result.json"
    record.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    started = time.monotonic()
    print(f"测试日志：{output / 'tests.log'}", flush=True)
    code = 1
    try:
        with (output / "tests.log").open("wb") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "KNOWREALM_TEST_DIAGNOSTICS_DIR": str(output.resolve()),
                },
                start_new_session=os.name != "nt",
            )
            metadata["pid"] = process.pid
            record.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            try:
                code = process.wait(timeout=timeout)
                metadata["status"] = "PASSED" if code == 0 else "FAILED"
            except subprocess.TimeoutExpired:
                metadata["status"] = "TIMED_OUT"
                code = 124
                stop(process)
            except KeyboardInterrupt:
                metadata["status"] = "INTERRUPTED"
                code = 130
                stop(process)
            metadata["exit_code"] = process.returncode
    except OSError as exc:
        if "pid" not in metadata:
            metadata["status"] = "START_FAILED"
        metadata["error"] = str(exc)
    finally:
        metadata["finished_at"] = datetime.now(UTC).isoformat()
        metadata["elapsed_seconds"] = round(time.monotonic() - started, 2)
        record.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{metadata['status']}：{record}", flush=True)
        if metadata["status"] != "PASSED":
            log_path = output / "tests.log"
            if log_path.exists():
                print(
                    "\n".join(
                        log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
                    )
                )
    return code


def main() -> int:
    writer = cast("TextIOWrapper[BinaryIO]", sys.stdout)
    if hasattr(writer, "reconfigure"):
        writer.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("frontend", "backend", "all"))
    parser.add_argument("tests", nargs="*", help="文件或 pytest node ID；all 不接受筛选")
    parser.add_argument("--timeout", type=float, default=3600, help="每套测试的秒数上限")
    args = parser.parse_args()
    if args.timeout <= 0 or not args.timeout < float("inf"):
        parser.error("timeout 必须是有限正数")
    if args.suite == "all" and args.tests:
        parser.error("all 不接受筛选，请选择单个 suite")
    if any(
        not value or value.startswith("-") or any(c in value for c in '&|<>^%"\r\n()!')
        for value in args.tests
    ):
        parser.error("tests 只接受文件或 node ID，不接受命令选项或 Shell 字符")
    lock = FileLock(str(lock_path()), timeout=0, preserve_lock_file=True)
    try:
        lock.acquire()
    except Timeout:
        parser.exit(2, "当前仓库或其 worktree 已有测试运行，请等待其结束后重试。\n")
    try:
        return run_suites(args)
    finally:
        lock.release()


def run_suites(args: argparse.Namespace) -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    suites = ("frontend", "backend") if args.suite == "all" else (args.suite,)
    exit_code = 0
    for suite in suites:
        output = ROOT / ".pytest-tmp-runs" / run_id / suite
        if suite == "frontend":
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                print("未找到 pnpm", file=sys.stderr)
                return 2
            cwd = ROOT / "apps" / "desktop"
            command = [
                pnpm,
                "exec",
                "vitest",
                "run",
                "--maxWorkers=1",
                "--reporter=verbose",
                *args.tests,
            ]
        else:
            cwd = ROOT / "backend"
            command = [
                sys.executable,
                "-u",
                "-m",
                "pytest",
                "-vv",
                "--tb=short",
                "--durations=10",
                "-o",
                "faulthandler_timeout=120",
                f"--basetemp={cwd / ('.pytest-tmp-run-' + run_id)}",
                *args.tests,
            ]
        result = run(command, cwd, output, args.timeout)
        if result in (124, 130):
            return result
        exit_code = exit_code or result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
