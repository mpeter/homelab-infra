#!/usr/bin/env bash
set -euo pipefail

# Pipe `tofu show -json saved.tfplan` here; never save the JSON containing secrets.
mode=${1:-}
[[ -z $mode || $mode == --disposable-destroy ]] || {
  echo 'usage: check-plan.sh [--disposable-destroy] < plan.json' >&2
  exit 2
}

if ! jq -e --arg mode "$mode" '
  type == "object" and
  (.format_version | type == "string") and
  (.resource_changes | type == "array") and
  (
    if $mode == "--disposable-destroy" then
      (.resource_changes | length == 1) and
      (.resource_changes[0].address == "proxmox_virtual_environment_vm.disposable") and
      (.resource_changes[0].type == "proxmox_virtual_environment_vm") and
      (.resource_changes[0].change.actions == ["delete"])
    else
      all(.resource_changes[];
        .type == "proxmox_virtual_environment_vm" and
        (
          .change.actions == ["no-op"] or
          .change.actions == ["create"] or
          .change.actions == ["update"]
        )
      )
    end
  )
' >/dev/null 2>&1; then
  echo 'plan gate rejected unexpected resource type or action' >&2
  exit 1
fi

echo 'plan gate PASS'
