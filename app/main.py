import json
import sys

from openai import OpenAI

from config import DEFAULT_MODEL
from tools import (
    get_zabbix_packages,
    get_zabbix_version,
    require_approval,
    run_backup,
    run_postcheck,
    run_precheck,
    run_upgrade,
    run_switch_repo
)

client = OpenAI()

SYSTEM_PROMPT = """
You are an infrastructure upgrade assistant for Zabbix.

Rules:
- Analyze the provided tool results.
- Summarize clearly for a human operator.
- Be operationally precise.
- If any tool result shows a non-zero return code, explain the failure and recommend the next safe step.
- Do not invent actions that were not run.
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


def prepare_upgrade_workflow(host: str = "zabbix") -> None:
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
            "Summarize the current Zabbix upgrade readiness for this host. "
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

def execute_upgrade_workflow(host: str = "zabbix") -> None:
    print("\n=== STEP 1: VERSION CHECK ===\n")
    version_result = get_zabbix_version(host=host)
    print(json.dumps(version_result, indent=2))

    print("\n=== STEP 2: APPROVAL GATE FOR REPO SWITCH ===\n")
    repo_approval = require_approval(
        action_summary=(
            f"Switch host '{host}' from Zabbix 7.2 repository to Zabbix 7.4 repository "
            "before attempting package upgrade."
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
            f"Run upgrade playbook for host '{host}' after successful repo switch to 7.4."
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
            "State whether the host appears to have moved from 7.2 toward 7.4, "
            "highlight any failures, and recommend the next safe operational step."
        ),
        context=final_context,
    )
    print(final_summary)

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

    print("Unsupported command pattern for this workflow version.")
    print('Try: python3 main.py "Prepare for a Zabbix upgrade on host zabbix"')
    print('Or:  python3 main.py "Execute the Zabbix upgrade on host zabbix"')


if __name__ == "__main__":
    main()
