#!/usr/bin/env python3
"""
Ralph - 自主 AI Agent 循环执行器
Windows 兼容版：去掉 Unix PTY 依赖，用临时文件传 prompt
"""

import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dashboard

# 修复 Windows 控制台编码
if platform.system() == "Windows":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 配置
MAX_ITERATIONS = 50
TIMEOUT_SECONDS = 30 * 60

AGENT = sys.argv[1] if len(sys.argv) > 1 else "claude"
IS_WINDOWS = platform.system() == "Windows"

# 目录配置
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CLAUDE_INSTRUCTION_FILE = SCRIPT_DIR / "CLAUDE.md"
VALIDATOR_INSTRUCTION_FILE = SCRIPT_DIR / "VALIDATOR.md"
PRD_FILE = SCRIPT_DIR / "prd.json"


def spawn_agent(prompt: str) -> subprocess.Popen:
    """
    启动 AI Agent 子进程。
    Windows: 写临时文件，通过 type 管道传入
    Unix: 使用 script 提供 PTY
    """
    if IS_WINDOWS:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(prompt)
        tmp.close()

        if AGENT == "codex":
            cmd_str = f'type "{tmp.name}" | codex exec --dangerously-bypass-approvals-and-sandbox'
        else:
            cmd_str = f'type "{tmp.name}" | claude --print --dangerously-skip-permissions'

        proc = subprocess.Popen(
            cmd_str,
            cwd=str(PROJECT_ROOT),
            stdout=sys.stdout,
            stderr=sys.stderr,
            shell=True,
        )
        return proc, tmp.name
    else:
        if AGENT == "codex":
            cmd = ["script", "-q", "/dev/null", "codex", "exec",
                   "--dangerously-bypass-approvals-and-sandbox", prompt]
        else:
            cmd = ["script", "-q", "/dev/null", "claude", "--print",
                   "--dangerously-skip-permissions", prompt]

        proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
        return proc, None


def run_developer(iteration: int) -> bool:
    """调用开发 Agent，返回是否超时"""
    print(f"\n{'='*64}")
    print(f"  Developer | Round {iteration}/{MAX_ITERATIONS}")
    print(f"{'='*64}")

    if not CLAUDE_INSTRUCTION_FILE.exists():
        print(f"[ERROR] {CLAUDE_INSTRUCTION_FILE} not found")
        return False

    prompt = CLAUDE_INSTRUCTION_FILE.read_text(encoding="utf-8")
    process, tmp_path = spawn_agent(prompt)

    start_time = time.time()
    try:
        while True:
            ret_code = process.poll()
            if ret_code is not None:
                print(f"\n[OK] Developer done (exit: {ret_code})")
                return False

            elapsed = time.time() - start_time
            if elapsed > TIMEOUT_SECONDS:
                print(f"\n[WARN] Developer timeout ({int(elapsed)}s)")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                print("   Process killed, will retry next round")
                return True

            time.sleep(30)
    except Exception as e:
        print(f"\n[ERROR] Developer: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def run_validator(iteration: int) -> None:
    """调用 Validator Agent"""
    print(f"\n{'='*64}")
    print(f"  Validator | Round {iteration}")
    print(f"{'='*64}")

    if not VALIDATOR_INSTRUCTION_FILE.exists():
        print(f"[WARN] {VALIDATOR_INSTRUCTION_FILE} not found, skip validation")
        return

    prompt = VALIDATOR_INSTRUCTION_FILE.read_text(encoding="utf-8")
    process, tmp_path = spawn_agent(prompt)

    start_time = time.time()
    try:
        while True:
            ret_code = process.poll()
            if ret_code is not None:
                print(f"\n[OK] Validator done (exit: {ret_code})")
                return

            elapsed = time.time() - start_time
            if elapsed > TIMEOUT_SECONDS * 2:
                print(f"\n[WARN] Validator timeout ({int(elapsed)}s)")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                print("   Validator killed, skip")
                return

            time.sleep(30)
    except Exception as e:
        print(f"\n[ERROR] Validator: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def get_current_story_id() -> str | None:
    try:
        prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
        for story in prd.get("userStories", []):
            if not story.get("passes", False) and not story.get("blocked", False):
                return story.get("id")
    except Exception:
        pass
    return None


def all_stories_resolved() -> bool:
    try:
        prd = json.loads(PRD_FILE.read_text(encoding="utf-8"))
        for story in prd.get("userStories", []):
            if not story.get("passes", False) and not story.get("blocked", False):
                return False
        return True
    except Exception as e:
        print(f"[WARN] prd.json read failed: {e}")
        return False


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def main():
    print(f"{'='*64}")
    print(f"  Ralph - AI Agent Automation")
    print(f"  Platform: {platform.system()} | Agent: {AGENT}")
    print(f"  Project:  {PROJECT_ROOT}")
    print(f"  Pending:  {get_current_story_id() or 'none'}")
    print(f"  Max Iter: {MAX_ITERATIONS}")
    print(f"{'='*64}")

    total_start = time.time()

    dashboard.start(max_iterations=MAX_ITERATIONS, open_browser=True)

    for i in range(1, MAX_ITERATIONS + 1):
        try:
            story = get_current_story_id()
            if not story:
                print("\n[DONE] No pending stories")
                break

            print(f"\n>> Story: {story}")

            # Step 1: Developer
            dashboard.set_state(iteration=i, phase="developing", current_story=story)
            timed_out = run_developer(i)
            if timed_out:
                dashboard.set_state(phase="idle")
                print("[SKIP] Developer timeout, skip validator")
                time.sleep(2)
                continue

            # Step 2: Validator
            dashboard.set_state(phase="validating")
            run_validator(i)

            # Step 3: Check completion
            dashboard.set_state(phase="idle")
            if all_stories_resolved():
                dashboard.set_state(phase="done")
                elapsed = time.time() - total_start
                print(f"\n{'='*64}")
                print(f"  ALL DONE! Time: {format_duration(elapsed)}")
                print(f"{'='*64}")
                sys.exit(0)

        except KeyboardInterrupt:
            elapsed = time.time() - total_start
            print(f"\n[INT] User interrupt | Time: {format_duration(elapsed)}")
            sys.exit(130)

    elapsed = time.time() - total_start
    print(f"\nMax iterations ({MAX_ITERATIONS}) reached | Time: {format_duration(elapsed)}")
    sys.exit(1)


if __name__ == "__main__":
    main()
