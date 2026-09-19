# Networking plan

## Known current state

- PVE management address is recorded only in the ignored local inventory.
- iDRAC management address is recorded only in the ignored local inventory.
- Gateway and DNS addresses remain local configuration inputs.
- Active Brocade port: `1/2/2`, access/PVID VLAN 1
- VLAN 128 was retired from the lab path.
- Hardware includes four Broadcom 10 GbE ports and a Mellanox ConnectX-3.

## Target design

Use a VLAN-aware Proxmox bridge over a two-port active-backup bond. Preserve a
known-good management path while introducing the bond and trunk. A second link
protects against a port, optic, or cable failure; it does not make the Brocade
switch redundant.

Proposed logical networks:

| VLAN | Purpose | Exposure |
|---:|---|---|
| Management VLAN to be selected | PVE, iDRAC, switch, UPS | Administrators and automation only |
| 20 | Development systems | Trusted user network |
| 30 | OpenShift and disposable labs | Controlled east-west access |
| 40 | Shared services such as IdM, DNS, registry, AAP | Explicit service rules |
| 50 | Backup and storage traffic | Backup systems and hypervisor only |

The VLAN IDs are proposals until reconciled with the existing UniFi and Brocade
configuration. Subnets, DHCP scopes, reservations, and the internal domain must
be decided together before automation creates guests.

## Management access

- Reach PVE and iDRAC through the trusted LAN or VPN.
- Use internal DNS names and trusted certificates.
- Do not publish either interface directly to the internet.
- Create named administrator accounts and narrowly scoped automation tokens.
- Preserve a tested emergency local credential outside the automation system.

## Configuration ownership

| Surface | Desired-state owner | Operational owner | Adoption rule |
|---|---|---|---|
| Brocade switch | AAP project and reviewed CLI templates | AAP jobs over SSH | Back up and normalize the running configuration before the first write |
| UniFi networks, WLANs, DHCP, DNS, and firewall policy | Dedicated OpenTofu state | AAP backup and health jobs | Import existing objects before any apply |
| Proxmox bridges, bonds, and VM interfaces | OpenTofu Proxmox state | AAP verification jobs | Preserve the current management path until the replacement passes tests |
| Guest network configuration | cloud-init, Ignition, then AAP | AAP | Change only after the upstream VLAN and routing path exists |

The UniFi provider is selected only after recording the controller product,
version, and available API. The former
[`paultyng/unifi` provider](https://github.com/paultyng/terraform-provider-unifi)
is archived; its name must not be copied into a new stack by habit. Evaluate a
current Integration API provider and the community fork against a read-only
export, then pin the chosen provider and document the result.

The historical Ansible
[`community.network` ICX collection](https://github.com/ansible-collections/community.network)
is also archived and its ICX modules are deprecated. If the exact switch and
firmware pass a compatibility test, pin the last usable release in a
Brocade-only execution environment. Otherwise use reviewed `ansible.netcommon`
CLI operations or a small adapter with captured-output tests. Do not let this
legacy dependency enter the general RHEL or platform execution environment.

## Change and recovery protocol

1. Capture controller and switch versions, running configuration, object IDs,
   port state, VLAN membership, DHCP scopes, firewall rules, and topology.
2. Store raw backups in encrypted off-host storage. Commit only reviewed desired
   state with credentials, password hashes, private keys, and sensitive exports
   removed.
3. Prove read-only access with dedicated automation identities.
4. Import UniFi objects into a separate state backend and require a no-change
   plan before edits.
5. Render and review Brocade commands, take a fresh backup, then apply a single
   bounded change through an AAP workflow.
6. Read back the affected controller objects and switch commands, then test the
   permitted and denied traffic paths.
7. Restore the previous configuration through the out-of-band path if
   management reachability or policy validation fails.

The initial Brocade work must leave port `1/2/2` and the current PVE management
path intact until the redundant bond and trunk are proven. iDRAC or a physical
console is the rescue path for host-network changes; the switch must also have
a tested console or configuration-reload recovery procedure before disruptive
automation is enabled.

## Automation identities

- Use a named, least-privileged UniFi API identity or API key supported by the
  selected provider. Do not automate with a personal administrator session.
- Prefer SSH keys for the Brocade automation identity. Store enable credentials,
  if required, only in AAP credentials or an encrypted secret store.
- Keep endpoints and exact device inventory in `inventory/local/`, which is
  excluded from Git.
- Keep emergency credentials outside AAP so recovery does not depend on the
  platform being healthy.

## Future experiments

- Compare VirtIO and SR-IOV networking for selected VMs.
- Reserve direct device assignment for workloads that can tolerate reduced
  migration flexibility.
- Use the Mellanox adapter for a dedicated backup/storage path or lab testing
  after the primary bridge is stable.
- Work through the staged ICX experiments in
  [`brocade-projects.md`](brocade-projects.md), starting with read-only inventory
  and telemetry.
