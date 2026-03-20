import re
import urllib.request
from urllib.error import URLError, HTTPError
import json
import shlex
import copy
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PATTERNS = [
    r"(?im)^(\s*DBPassword\s*=\s*)(.+)$",
    r"(?im)^(\s*VaultToken\s*=\s*)(.+)$",
    r"(?im)^(\s*TLSPSKIdentity\s*=\s*)(.+)$",
    r"(?im)^(\s*TLSPSKFile\s*=\s*)(.+)$",
    r"(?im)^(\s*Password\s*=\s*)(.+)$",
    r"(?im)^(\s*ApiKey\s*=\s*)(.+)$",
    r"(?im)^(\s*Secret\s*=\s*)(.+)$",
    r"(?im)^(\s*Token\s*=\s*)(.+)$",
]

SENSITIVE_INLINE_PATTERNS = [
    r"(?im)(DBPassword=)([^\s#]+)",
    r"(?im)(VaultToken=)([^\s#]+)",
    r"(?im)(TLSPSKIdentity=)([^\s#]+)",
    r"(?im)(TLSPSKFile=)([^\s#]+)",
]


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text

    redacted = text

    for pattern in SENSITIVE_KEY_PATTERNS:
        redacted = re.sub(pattern, r"\1<REDACTED>", redacted)

    for pattern in SENSITIVE_INLINE_PATTERNS:
        redacted = re.sub(pattern, r"\1<REDACTED>", redacted)

    return redacted


def sanitize_for_logging(value):
    """
    Recursively sanitize strings inside dict/list structures before printing,
    logging, or sending to the model.
    """
    if isinstance(value, str):
        return redact_sensitive_text(value)

    if isinstance(value, dict):
        return {k: sanitize_for_logging(v) for k, v in value.items()}

    if isinstance(value, list):
        return [sanitize_for_logging(v) for v in value]

    return value


def sanitize_command_result(result: dict) -> dict:
    clean = copy.deepcopy(result)
    if "stdout" in clean:
        clean["stdout"] = redact_sensitive_text(clean["stdout"])
    if "stderr" in clean:
        clean["stderr"] = redact_sensitive_text(clean["stderr"])
    return clean

from config import (
    ANSIBLE_ROOT,
    DEFAULT_HOST,
    INVENTORY_FILE,
    PLAYBOOK_BACKUP,
    PLAYBOOK_POSTCHECK,
    PLAYBOOK_PRECHECK,
    PLAYBOOK_SWITCH_REPO,
    PLAYBOOK_UPGRADE,
    RUN_LOG_DIR,
    ZABBIX_SERVER_CONF,
    ZABBIX_SERVER_CONF_DIST,
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

def _write_sanitized_run_log(tool_name: str, payload: dict) -> None:
    _write_run_log(tool_name, sanitize_for_logging(payload))

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

def get_official_zabbix_upgrade_note_urls(
    from_version: str = "7.2",
    to_version: str = "7.4",
) -> dict[str, Any]:
    """
    Return official Zabbix documentation URLs relevant for this upgrade path.
    """
    result = {
        "from_version": from_version,
        "to_version": to_version,
        "urls": {
            "major_upgrade_notes": "https://www.zabbix.com/documentation/current/en/manual/installation/upgrade_notes",
            "minor_upgrade_notes": "https://www.zabbix.com/documentation/current/en/manual/installation/upgrade_notes_minor",
            "debian_ubuntu_upgrade_guide": "https://www.zabbix.com/documentation/current/en/manual/installation/upgrade/packages/debian_ubuntu",
            "upgrade_overview": "https://www.zabbix.com/documentation/current/en/manual/installation/upgrade",
        },
        "note": "Official Zabbix documentation URLs for upgrade planning.",
    }
    _write_run_log("get_official_zabbix_upgrade_note_urls", result)
    return result


def fetch_official_url_text(url: str) -> dict[str, Any]:
    """
    Fetch text from an allowed official Zabbix documentation URL and return a sanitized excerpt.
    """
    allowed_prefixes = (
        "https://www.zabbix.com/documentation/",
        "https://www.zabbix.com/release_notes",
        "https://www.zabbix.com/rn/",
    )

    if not url.startswith(allowed_prefixes):
        result = {
            "url": url,
            "returncode": 1,
            "error": "URL is not in the allowlist of official Zabbix documentation domains/paths.",
        }
        _write_run_log("fetch_official_url_text", result)
        return result

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "zabbix-ai-upgrade-workflow/1.0"
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")

        # Very simple HTML-to-text cleanup for first version.
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        result = {
            "url": url,
            "returncode": 0,
            "content_type": content_type,
            "text_excerpt": text[:20000],
            "text_length": len(text),
        }
        _write_run_log("fetch_official_url_text", result)
        return result

    except HTTPError as exc:
        result = {
            "url": url,
            "returncode": 1,
            "error": f"HTTPError: {exc.code} {exc.reason}",
        }
        _write_run_log("fetch_official_url_text", result)
        return result
    except URLError as exc:
        result = {
            "url": url,
            "returncode": 1,
            "error": f"URLError: {exc.reason}",
        }
        _write_run_log("fetch_official_url_text", result)
        return result
    except Exception as exc:
        result = {
            "url": url,
            "returncode": 1,
            "error": f"Unexpected error: {exc}",
        }
        _write_run_log("fetch_official_url_text", result)
        return result

def read_remote_file(
    path: str,
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    cmd = [
        "ansible",
        host,
        "-i",
        str(INVENTORY_FILE),
        "-b",
        "-m",
        "shell",
        "-a",
        f"cat {shlex.quote(path)}",
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    safe_result = sanitize_command_result(result)

    payload = {
        "host": host,
        "path": path,
        **safe_result,
    }
    _write_sanitized_run_log("read_remote_file", payload)
    return payload

def get_remote_unified_diff(
    left_path: str,
    right_path: str,
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    cmd = [
        "ansible",
        host,
        "-i",
        str(INVENTORY_FILE),
        "-b",
        "-m",
        "shell",
        "-a",
        (
            f"diff -u {shlex.quote(left_path)} {shlex.quote(right_path)} || true"
        ),
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)
    safe_result = sanitize_command_result(result)

    payload = {
        "host": host,
        "left_path": left_path,
        "right_path": right_path,
        **safe_result,
    }
    _write_sanitized_run_log("get_remote_unified_diff", payload)
    return payload

def check_remote_file_exists(
    path: str,
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    cmd = [
        "ansible",
        host,
        "-i",
        str(INVENTORY_FILE),
        "-b",
        "-m",
        "shell",
        "-a",
        f"test -f {shlex.quote(path)}",
    ]
    result = _run_command(cmd, cwd=ANSIBLE_ROOT)

    payload = {
        "host": host,
        "path": path,
        "exists": result["returncode"] == 0,
        **sanitize_command_result(result),
    }
    _write_sanitized_run_log("check_remote_file_exists", payload)
    return payload


def get_zabbix_server_conf_paths(host: str = DEFAULT_HOST) -> dict[str, Any]:
    result = {
        "host": host,
        "active_config": ZABBIX_SERVER_CONF,
        "package_dist_config": ZABBIX_SERVER_CONF_DIST,
    }
    _write_run_log("get_zabbix_server_conf_paths", result)
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
