#!/usr/bin/env bash
set -euo pipefail

checker=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/check-plan.sh

expect_status() {
  local expected=$1 input=$2
  shift 2
  local actual=0
  bash "$checker" "$@" <<< "$input" >/dev/null 2>&1 || actual=$?
  [[ $actual == "$expected" ]] || {
    printf 'expected exit %s, got %s for %s\n' "$expected" "$actual" "$input" >&2
    exit 1
  }
}

expect_status 0 '{"format_version":"1.2","resource_changes":[]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.disposable","type":"proxmox_virtual_environment_vm","change":{"actions":["create"]}}]}'
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_storage_zfspool.bad","type":"proxmox_storage_zfspool","change":{"actions":["create"]}}]}'
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.fedora","type":"proxmox_virtual_environment_vm","change":{"actions":["delete","create"]}}]}'
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.disposable","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.disposable","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}' --disposable-destroy
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.fedora","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}' --disposable-destroy
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_virtual_environment_vm.disposable","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}},{"address":"proxmox_virtual_environment_vm.other","type":"proxmox_virtual_environment_vm","change":{"actions":["create"]}}]}' --disposable-destroy
expect_status 1 '{not json}'
expect_status 1 '{"format_version":"1.2"}'
printf 'plan gate tests PASS\n'
