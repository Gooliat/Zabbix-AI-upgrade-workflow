import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    ANSIBLE_ROOT,
    DEFAULT_HOST,
    INVENTORY_FILE,
    PLAYBOOK_BACKUP,
    PLAYBOOK_POSTCHECK,
    PLAYBOOK_PRECHECK,
    PLAYBOOK_UPGRADE,
    RUN_LOG_DIR,
    PLAYBOOK_SWITCH_REPO,
)

def run_switch_repo(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_FILE),
        str(PLAYBOOK_SWITCH_REPO),
        "--limit",
        host,
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("run_switch_repo", result)
    return result

def _run_command(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run a local command and return a structured result."""
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    return {
        "command": " ".join(shlex.quote(part) for part in cmd),
        "returncode": result.returncode,
        "stdout": result.stdout[-20000:],
        "stderr": result.stderr[-20000:],
    }


def _write_run_log(tool_name: str, payload: dict[str, Any]) -> None:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = RUN_LOG_DIR / f"{ts}_{tool_name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_zabbix_version(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible",
        host,
        "-i",
        str(INVENTORY_FILE),
        "-m",
        "shell",
        "-a",
        "zabbix_server --version | head -n 2",
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("get_zabbix_version", result)
    return result


def get_zabbix_packages(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible",
        host,
        "-i",
        str(INVENTORY_FILE),
        "-m",
        "shell",
        "-a",
        r"dpkg -l | grep -E '^ii\s+zabbix'",
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("get_zabbix_packages", result)
    return result


def run_precheck(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_FILE),
        str(PLAYBOOK_PRECHECK),
        "--limit",
        host,
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("run_precheck", result)
    return result


def run_backup(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_FILE),
        str(PLAYBOOK_BACKUP),
        "--limit",
        host,
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("run_backup", result)
    return result

def run_upgrade(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_FILE),
        str(PLAYBOOK_UPGRADE),
        "--limit",
        host,
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("run_upgrade", result)
    return result


def run_postcheck(host: str = DEFAULT_HOST) -> dict[str, Any]:
    cmd = [
        "ansible-playbook",
        "-i",
        str(INVENTORY_FILE),
        str(PLAYBOOK_POSTCHECK),
        "--limit",
        host,
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    _write_run_log("run_postcheck", result)
    return result

def require_approval(action_summary: str) -> dict[str, Any]:
    print("\n=== APPROVAL REQUIRED ===")
    print(action_summary)
    answer = input("Type APPROVE to continue: ").strip()
    approved = answer == "APPROVE"
    result = {
        "approved": approved,
        "input": answer,
        "action_summary": action_summary,
    }
    _write_run_log("require_approval", result)
    return result
