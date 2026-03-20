from pathlib import Path

APP_ROOT = Path("/home/ansible/zabbix-ai/app")
ANSIBLE_ROOT = Path("/home/ansible/zabbix-ai/ansible")
RUN_LOG_DIR = APP_ROOT / "run_logs"

DEFAULT_MODEL = "gpt-5.4"

INVENTORY_FILE = ANSIBLE_ROOT / "inventory" / "staging.ini"

PLAYBOOK_PRECHECK = ANSIBLE_ROOT / "playbooks" / "precheck.yml"
PLAYBOOK_BACKUP = ANSIBLE_ROOT / "playbooks" / "backup.yml"
PLAYBOOK_UPGRADE = ANSIBLE_ROOT / "playbooks" / "upgrade_server.yml"
PLAYBOOK_POSTCHECK = ANSIBLE_ROOT / "playbooks" / "postcheck.yml"
PLAYBOOK_SWITCH_REPO = ANSIBLE_ROOT / "playbooks" / "switch_repo_7_4.yml"

DEFAULT_HOST = "zabbix"

ZABBIX_SERVER_CONF = "/etc/zabbix/zabbix_server.conf"
ZABBIX_SERVER_CONF_DIST = "/etc/zabbix/zabbix_server.conf.dpkg-dist"
