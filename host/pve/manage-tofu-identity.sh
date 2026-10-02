#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
[[ $mode == check || $mode == apply ]] || {
  echo 'usage: manage-tofu-identity.sh check|apply' >&2
  exit 2
}

pve_host=192.168.0.188
pve_user=tofu@pve
token_id=opentofu
pool_id=tofu-vms
role_id=OpenTofuVM
storage_role=OpenTofuStorage
network_role=OpenTofuNetwork
mapping_role=OpenTofuMappingUse
read_role=OpenTofuRead
mapping_id=nas-hba
vm_privs='VM.Allocate VM.Audit VM.Config.CPU VM.Config.Memory VM.Config.Disk VM.Config.Network VM.Config.Options VM.Config.Cloudinit VM.Config.HWType VM.GuestAgent.Audit VM.PowerMgmt Pool.Audit'
storage_privs='Datastore.AllocateSpace Datastore.Audit'
network_privs='SDN.Audit SDN.Use'
mapping_privs='Mapping.Use'
read_privs='Sys.Audit'

export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }
pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$@"; }
fail() { printf 'PVE OpenTofu identity %s: %s\n' "$mode" "$*" >&2; exit 1; }

if [[ $mode == check ]]; then
  pve "pvesh get /pools --output-format json" | jq -e --arg pool "$pool_id" 'any(.[]; .poolid == $pool)' >/dev/null || fail 'dedicated pool is missing'
  pve "pveum user list --output-format json" | jq -e --arg user "$pve_user" 'any(.[]; .userid == $user and .enable == 1)' >/dev/null || fail 'dedicated user is missing or disabled'
  pve "pveum user token list $pve_user --output-format json" | jq -e --arg token "$token_id" 'any(.[]; .tokenid == $token and .privsep == 1)' >/dev/null || fail 'privilege-separated API token is missing'
  pve "pveum role list --output-format json" | jq -e --arg role "$role_id" --arg privs "$vm_privs" 'any(.[]; .roleid == $role and ((.privs | split(",") | sort) == ($privs | split(" ") | sort)))' >/dev/null || fail 'VM role privileges differ'
  pve "pveum role list --output-format json" | jq -e --arg role "$storage_role" --arg privs "$storage_privs" 'any(.[]; .roleid == $role and ((.privs | split(",") | sort) == ($privs | split(" ") | sort)))' >/dev/null || fail 'storage role privileges differ'
  pve "pveum role list --output-format json" | jq -e --arg role "$network_role" --arg privs "$network_privs" 'any(.[]; .roleid == $role and ((.privs | split(",") | sort) == ($privs | split(" ") | sort)))' >/dev/null || fail 'network role privileges differ'
  pve "pveum role list --output-format json" | jq -e --arg role "$mapping_role" --arg privs "$mapping_privs" 'any(.[]; .roleid == $role and ((.privs | split(",") | sort) == ($privs | split(" ") | sort)))' >/dev/null || fail 'PCI mapping role privileges differ'
  pve "pveum role list --output-format json" | jq -e --arg role "$read_role" --arg privs "$read_privs" 'any(.[]; .roleid == $role and ((.privs | split(",") | sort) == ($privs | split(" ") | sort)))' >/dev/null || fail 'read role privileges differ'
  acls=$(pve 'pveum acl list --output-format json')
  require_acl() {
    local path=$1 role=$2 type=$3 principal=$4
    jq -e --arg path "$path" --arg role "$role" --arg type "$type" --arg principal "$principal" \
      'any(.[]; .path == $path and .roleid == $role and .type == $type and .ugid == $principal and .propagate == 1)' \
      <<< "$acls" >/dev/null || fail "missing $type ACL at $path for $role"
  }
  require_acl "/pool/$pool_id" "$role_id" user "$pve_user"
  require_acl "/pool/$pool_id" "$role_id" token "$pve_user!$token_id"
  require_acl /storage/fast-vm "$storage_role" user "$pve_user"
  require_acl /storage/fast-vm "$storage_role" token "$pve_user!$token_id"
  require_acl /storage/local "$storage_role" user "$pve_user"
  require_acl /storage/local "$storage_role" token "$pve_user!$token_id"
  require_acl /sdn/zones/localnetwork/vmbr0 "$network_role" user "$pve_user"
  require_acl /sdn/zones/localnetwork/vmbr0 "$network_role" token "$pve_user!$token_id"
  require_acl "/mapping/pci/$mapping_id" "$mapping_role" user "$pve_user"
  require_acl "/mapping/pci/$mapping_id" "$mapping_role" token "$pve_user!$token_id"
  require_acl / "$read_role" user "$pve_user"
  require_acl / "$read_role" token "$pve_user!$token_id"
  permissions=$(pve "pveum user token permissions $pve_user $token_id --output-format json")
  jq -e 'all(.[]; (has("Pool.Allocate") | not) and (has("Datastore.Allocate") | not) and (has("Sys.Modify") | not) and (has("Sys.PowerMgmt") | not))' \
    <<< "$permissions" >/dev/null || fail 'token has a forbidden pool, storage, or host privilege'
  jq -e 'all(.[]; has("Mapping.Modify") | not)' <<< "$permissions" >/dev/null || fail 'token has PCI mapping administration privilege'
  printf 'PVE OpenTofu identity check PASS\n'
  exit 0
fi

pool_json=$(pve 'pvesh get /pools --output-format json')
if ! jq -e --arg pool "$pool_id" 'any(.[]; .poolid == $pool)' <<< "$pool_json" >/dev/null; then
  pve "pveum pool add $pool_id --comment 'OpenTofu-managed VM pool'"
fi

users=$(pve 'pveum user list --output-format json')
if ! jq -e --arg user "$pve_user" 'any(.[]; .userid == $user)' <<< "$users" >/dev/null; then
  pve "pveum user add $pve_user --comment 'Scoped OpenTofu VM automation'"
fi

roles=$(pve 'pveum role list --output-format json')
set_role() {
  local role=$1 privs=$2
  if jq -e --arg role "$role" 'any(.[]; .roleid == $role)' <<< "$roles" >/dev/null; then
    pve "pveum role modify $role --privs '$privs'"
  else
    pve "pveum role add $role --privs '$privs'"
  fi
}
set_role "$role_id" "$vm_privs"
set_role "$storage_role" "$storage_privs"
set_role "$network_role" "$network_privs"
set_role "$mapping_role" "$mapping_privs"
set_role "$read_role" "$read_privs"

tokens=$(pve "pveum user token list $pve_user --output-format json")
if ! jq -e --arg token "$token_id" 'any(.[]; .tokenid == $token)' <<< "$tokens" >/dev/null; then
  token_json=$(pve "pveum user token add $pve_user $token_id --privsep 1 --comment 'OpenTofu VM lifecycle' --output-format json")
  token_secret=$(jq -er '.value' <<< "$token_json") || fail 'PVE did not return the new token value'
  printf '%s' "$token_secret" | secret-tool store --label='R720 PVE OpenTofu API token' homelab pve-tofu-api-token >/dev/null
  unset token_secret token_json
fi

pve "pveum acl modify /pool/$pool_id --users $pve_user --roles $role_id"
pve "pveum acl modify /pool/$pool_id --tokens $pve_user!$token_id --roles $role_id"
pve "pveum acl modify /storage/fast-vm --users $pve_user --roles $storage_role"
pve "pveum acl modify /storage/fast-vm --tokens $pve_user!$token_id --roles $storage_role"
pve "pveum acl modify /storage/local --users $pve_user --roles $storage_role"
pve "pveum acl modify /storage/local --tokens $pve_user!$token_id --roles $storage_role"
pve "pveum acl modify /sdn/zones/localnetwork/vmbr0 --users $pve_user --roles $network_role"
pve "pveum acl modify /sdn/zones/localnetwork/vmbr0 --tokens $pve_user!$token_id --roles $network_role"
pve "pveum acl modify /mapping/pci/$mapping_id --users $pve_user --roles $mapping_role"
pve "pveum acl modify /mapping/pci/$mapping_id --tokens $pve_user!$token_id --roles $mapping_role"
pve "pveum acl modify / --users $pve_user --roles $read_role"
pve "pveum acl modify / --tokens $pve_user!$token_id --roles $read_role"

bash "$0" check
