import json
import sys
import re
import yaml
from openai import OpenAI

from config import DEFAULT_MODEL, GROUP_VARS_FILE, DEFAULT_OUTPUT_LANGUAGE
from tools import (
    check_remote_file_exists,
    fetch_official_url_text,
    get_official_zabbix_upgrade_note_urls,
    get_remote_unified_diff,
    get_zabbix_packages,
    get_zabbix_server_conf_paths,
    get_zabbix_version,
    require_approval,
    run_backup,
    run_postcheck,
    run_precheck,
    run_switch_repo,
    run_upgrade,
    sanitize_for_logging,
)

client = OpenAI()

SYSTEM_PROMPT = f"""
You are an infrastructure upgrade assistant for Zabbix.

Rules:
- Analyze the provided tool results.
- Summarize clearly for a human operator.
- Be operationally precise.
- If any tool result shows a non-zero return code, explain the failure and recommend the next safe step.
- Do not invent actions that were not run.
- Write all operator-facing summaries in {DEFAULT_OUTPUT_LANGUAGE}.
- Keep commands, filenames, configuration keys, package names, and log excerpts in English when needed.
"""

def ask_model(prompt: str, context: dict) -> str:
    response = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    f"Structured context:\n{json.dumps(context, indent=2)}"
                ),
            }
        ],
    )
    return response.output_text


def extract_major_version(version_output: str) -> str | None:
    match = re.search(r"Zabbix\)\s+(\d+\.\d+)\.\d+", version_output)
    if match:
        return match.group(1)
    return None


def get_installed_major_version(host: str = "zabbix") -> tuple[dict, str | None]:
    version_result = get_zabbix_version(host=host)
    installed_major = extract_major_version(version_result.get("stdout", ""))
    return version_result, installed_major

def get_target_major_from_ansible() -> str:
    with open(GROUP_VARS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    target_major = data.get("zabbix_target_major")
    if not target_major:
        raise ValueError(
            f"zabbix_target_major is not defined in {GROUP_VARS_FILE}"
        )

    return str(target_major)

def prepare_upgrade_workflow(host: str = "zabbix", target_major: str | None = None) -> None:
    if target_major is None:
        target_major = get_target_major_from_ansible()
    print("\n=== STEP 1: COLLECT VERSION ===\n")
    version_result = get_zabbix_version(host=host)
    print(json.dumps(version_result, indent=2))

    print("\n=== STEP 2: COLLECT PACKAGE INFO ===\n")
    packages_result = get_zabbix_packages(host=host)
    print(json.dumps(packages_result, indent=2))

    print("\n=== STEP 3: RUN PRECHECK ===\n")
    precheck_result = run_precheck(host=host)
    print(json.dumps(precheck_result, indent=2))

    summary_context = {
        "host": host,
        "version_result": version_result,
        "packages_result": packages_result,
        "precheck_result": precheck_result,
    }

    print("\n=== STEP 4: AI SUMMARY ===\n")
    summary = ask_model(
        prompt=(
            f"Summarize the current Zabbix upgrade readiness for this host for an upgrade toward {target_major}. "
            "State whether the host looks ready for backup as the next step."
        ),
        context=summary_context,
    )
    print(summary)

    if (
        version_result.get("returncode", 1) != 0
        or packages_result.get("returncode", 1) != 0
        or precheck_result.get("returncode", 1) != 0
    ):
        print("\n=== WORKFLOW STOPPED ===\n")
        print("One or more prerequisite steps failed. Backup will not be attempted.")
        return

    print("\n=== STEP 5: APPROVAL GATE ===\n")
    approval_result = require_approval(
        action_summary=(
            f"Run backup playbook for host '{host}' as the next preparation step "
            "before Zabbix upgrade."
        )
    )
    print(json.dumps(approval_result, indent=2))

    if not approval_result.get("approved", False):
        print("\n=== WORKFLOW STOPPED ===\n")
        print("Approval was not granted. Backup was not run.")
        return

    print("\n=== STEP 6: RUN BACKUP ===\n")
    backup_result = run_backup(host=host)
    print(json.dumps(backup_result, indent=2))

    final_context = {
        "host": host,
        "version_result": version_result,
        "packages_result": packages_result,
        "precheck_result": precheck_result,
        "approval_result": approval_result,
        "backup_result": backup_result,
    }

    print("\n=== STEP 7: AI FINAL SUMMARY ===\n")
    final_summary = ask_model(
        prompt=(
            "Summarize the full prepare-for-upgrade workflow. "
            "Explain whether backup succeeded and what the next safe step would be."
        ),
        context=final_context,
    )
    print(final_summary)

def execute_upgrade_workflow(host: str = "zabbix", target_major: str | None = None) -> None:
    if target_major is None:
        target_major = get_target_major_from_ansible()
    print("\n=== STEP 1: VERSION CHECK ===\n")
    version_result = get_zabbix_version(host=host)
    print(json.dumps(version_result, indent=2))

    print("\n=== STEP 2: APPROVAL GATE FOR REPO SWITCH ===\n")
    repo_approval = require_approval(
        action_summary=(
            f"Switch host '{host}' to the Zabbix {target_major} repository before attempting package upgrade."
        )
    )
    print(json.dumps(repo_approval, indent=2))

    if not repo_approval.get("approved", False):
        print("\n=== WORKFLOW STOPPED ===\n")
        print("Approval was not granted. Repo switch was not run.")
        return

    print("\n=== STEP 3: SWITCH REPOSITORY TO 7.4 ===\n")
    repo_result = run_switch_repo(host=host)
    print(json.dumps(repo_result, indent=2))

    if repo_result.get("returncode", 1) != 0:
        print("\n=== WORKFLOW STOPPED ===\n")
        print("Repo switch failed. Upgrade will not be attempted.")
        return

    print("\n=== STEP 4: APPROVAL GATE FOR PACKAGE UPGRADE ===\n")
    upgrade_approval = require_approval(
        action_summary=(
            f"Run upgrade playbook for host '{host}' after successful repo switch to {target_major}."
        )
    )
    print(json.dumps(upgrade_approval, indent=2))

    if not upgrade_approval.get("approved", False):
        print("\n=== WORKFLOW STOPPED ===\n")
        print("Approval was not granted. Upgrade was not run.")
        return

    print("\n=== STEP 5: RUN UPGRADE ===\n")
    upgrade_result = run_upgrade(host=host)
    print(json.dumps(upgrade_result, indent=2))

    print("\n=== STEP 6: RUN POSTCHECK ===\n")
    postcheck_result = run_postcheck(host=host)
    print(json.dumps(postcheck_result, indent=2))

    final_context = {
        "host": host,
        "version_result": version_result,
        "repo_approval": repo_approval,
        "repo_result": repo_result,
        "upgrade_approval": upgrade_approval,
        "upgrade_result": upgrade_result,
        "postcheck_result": postcheck_result,
    }

    print("\n=== STEP 7: AI FINAL SUMMARY ===\n")
    final_summary = ask_model(
        prompt=(
            "Summarize the Zabbix repository switch and upgrade execution workflow. "
            "State whether the host appears to have moved toward the configured target version, "
            "highlight any failures, and recommend the next safe operational step."
        ),
        context=final_context,
    )
    print(final_summary)

def analyze_upgrade_notes_workflow(
    from_version: str,
    to_version: str | None = None,
) -> None:
    if to_version is None:
        to_version = get_target_major_from_ansible()
    print("\n=== STEP 1: GET OFFICIAL UPGRADE NOTE URLS ===\n")
    urls_result = get_official_zabbix_upgrade_note_urls(
        from_version=from_version,
        to_version=to_version,
    )
    print(json.dumps(urls_result, indent=2))

    urls = urls_result["urls"]

    print("\n=== STEP 2: FETCH MAJOR UPGRADE NOTES ===\n")
    major_notes = fetch_official_url_text(urls["major_upgrade_notes"])
    print(json.dumps(major_notes, indent=2))

    print("\n=== STEP 3: FETCH MINOR UPGRADE NOTES ===\n")
    minor_notes = fetch_official_url_text(urls["minor_upgrade_notes"])
    print(json.dumps(minor_notes, indent=2))

    print("\n=== STEP 4: FETCH DEBIAN/UBUNTU UPGRADE GUIDE ===\n")
    package_guide = fetch_official_url_text(urls["debian_ubuntu_upgrade_guide"])
    print(json.dumps(package_guide, indent=2))

    context = {
        "environment": {
            "os": "Ubuntu 24.04",
            "database": "PostgreSQL",
            "frontend": "Apache/PHP",
            "current_style": "Ansible playbooks with AI orchestration",
        },
        "from_version": from_version,
        "to_version": to_version,
        "urls_result": urls_result,
        "major_notes": major_notes,
        "minor_notes": minor_notes,
        "package_guide": package_guide,
    }

    print("\n=== STEP 5: AI ANALYSIS ===\n")
    analysis = ask_model(
        prompt=(
            "Read the provided official Zabbix upgrade notes and package upgrade guide. "
            "Summarize the breaking changes and critical upgrade considerations relevant "
            "to an Ubuntu 24.04, PostgreSQL, Apache/PHP Zabbix deployment. "
            "Also state what should be added or improved in our precheck, backup, upgrade, "
            "or postcheck playbooks/workflows."
        ),
        context=context,
    )
    print(analysis)

def analyze_zabbix_server_config_review_workflow(host: str = "zabbix") -> None:
    print("\n=== STEP 1: GET CONFIG PATHS ===\n")
    path_result = get_zabbix_server_conf_paths(host=host)
    print(json.dumps(path_result, indent=2))

    print("\n=== STEP 2: CHECK ACTIVE CONFIG EXISTS ===\n")
    active_exists = check_remote_file_exists(
        path=path_result["active_config"],
        host=host,
    )
    print(json.dumps(active_exists, indent=2))

    print("\n=== STEP 3: CHECK PACKAGE DIST CONFIG EXISTS ===\n")
    dist_exists = check_remote_file_exists(
        path=path_result["package_dist_config"],
        host=host,
    )
    print(json.dumps(dist_exists, indent=2))

    if not active_exists.get("exists", False):
        print("\n=== WORKFLOW STOPPED ===\n")
        print(f"Active config file does not exist: {path_result['active_config']}")
        return

    if not dist_exists.get("exists", False):
        print("\n=== WORKFLOW STOPPED ===\n")
        print(f"Package dist config file does not exist: {path_result['package_dist_config']}")
        return

    print("\n=== STEP 4: GET UNIFIED DIFF ===\n")
    diff_result = get_remote_unified_diff(
        left_path=path_result["active_config"],
        right_path=path_result["package_dist_config"],
        host=host,
    )
    print(json.dumps(sanitize_for_logging(diff_result), indent=2))

    context = {
        "host": host,
        "paths": path_result,
        "active_exists": active_exists,
        "dist_exists": dist_exists,
        "diff_result": diff_result,
        "environment": {
            "os": "Ubuntu 24.04",
            "role": "Zabbix server with PostgreSQL and Apache/PHP frontend",
            "upgrade_context": "Upgraded toward the configured target version",
        },
    }

    print("\n=== STEP 5: AI CONFIG REVIEW ===\n")
    analysis = ask_model(
        prompt=(
            "Analyze the provided unified diff between the active Zabbix server configuration "
            "and the package-provided .dpkg-dist file. Summarize the most important differences. "
            "Focus on new parameters, removed or relocated parameters, and anything relevant "
            "to security, TLS, frontend communication, or upgrade safety. "
            "Classify findings into: "
            "1) safe to ignore for now, "
            "2) should be reviewed soon, "
            "3) likely important to evaluate manually. "
            "Do not suggest blind merging. Be conservative and operationally practical."
        ),
        context=context,
    )
    print(analysis)

def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python3 main.py "Prepare upgrade on host zabbix"')
        sys.exit(1)

    user_input = sys.argv[1].lower()

    if "prepare" in user_input and "upgrade" in user_input:
        prepare_upgrade_workflow(host="zabbix")
        return

    if "execute" in user_input and "upgrade" in user_input:
        execute_upgrade_workflow(host="zabbix")
        return

    if "upgrade notes" in user_input or "release notes" in user_input:
        version_result, installed_major = get_installed_major_version(host="zabbix")

        if not installed_major:
            print("\n=== WORKFLOW STOPPED ===\n")
            print("Could not determine installed Zabbix major version from host output.")
            print(json.dumps(version_result, indent=2))
            return

        target_major = get_target_major_from_ansible()

        analyze_upgrade_notes_workflow(
            from_version=installed_major,
            to_version=target_major,
        )
        return

    if "config review" in user_input or "dpkg-dist" in user_input:
        analyze_zabbix_server_config_review_workflow(host="zabbix")
        return

    print("Unsupported command pattern for this workflow version.")
    print('Try: python3 main.py "Prepare for a Zabbix upgrade on host zabbix"')
    print('Or:  python3 main.py "Execute the Zabbix upgrade on host zabbix"')
    print('Or:  python3 main.py "Read the official Zabbix upgrade notes"')
    print('Or:  python3 main.py "Run a config review for zabbix_server.conf and dpkg-dist"')
    print('Or:  python3 main.py "Read the official Zabbix upgrade notes"')

if __name__ == "__main__":
    main()

