# Ansible Automation Platform

This directory will become the AAP project source for playbooks, roles,
rulebooks, execution-environment definitions, inventories, and declarative AAP
platform configuration.

The general execution environment should pin the Dell OpenManage, Proxmox,
Red Hat system roles, and `ansible.platform` collections plus the OpenTofu and
OpenShift CLIs required by approved workflows.

Network automation uses separate job templates:

| Job | Mode | Result |
|---|---|---|
| Brocade audit | Read only | Model, firmware, inventory, port/VLAN state, and reachability artifact |
| Brocade backup | Read only | Timestamped encrypted running and startup configuration backup |
| Brocade preview | Read only | Rendered commands and expected state delta |
| Brocade apply | Write | One approved bounded change with a fresh pre-change backup |
| Brocade verify | Read only | Command read-back plus traffic-path assertions |
| Brocade rollback | Write | Restore the approved prior configuration through the rescue procedure |
| UniFi backup and health | Read only | Controller backup, API health, and drift signal for the OpenTofu workflow |

The archived `community.network` ICX collection must not be added to the general
execution environment. A Brocade-only image may pin it after a compatibility
test against the exact switch firmware. Prefer SSH keys, AAP credential types,
approval nodes for disruptive jobs, and artifacts that expose commands without
exposing credentials.
