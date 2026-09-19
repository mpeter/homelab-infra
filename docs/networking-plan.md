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

## Future experiments

- Compare VirtIO and SR-IOV networking for selected VMs.
- Reserve direct device assignment for workloads that can tolerate reduced
  migration flexibility.
- Use the Mellanox adapter for a dedicated backup/storage path or lab testing
  after the primary bridge is stable.
