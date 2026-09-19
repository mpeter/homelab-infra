# OpenTofu

This directory will contain Proxmox and UniFi provider configuration, reusable
modules, and environment composition. It is intentionally empty until remote
encrypted state backends and automation identities are established.

OpenTofu will own Proxmox resources, not configuration inside guests. Plans are
reviewed before apply, and existing resources are imported before management.

Proxmox and UniFi use separate roots, state backends, locks, credentials, and
apply jobs. A compute plan must never be able to change the router, switches,
WLANs, DHCP, DNS, or firewall policy. A UniFi provider is added only after the
live controller version and API pass the compatibility gate described in
[the UniFi management contract](../network/unifi/README.md). Existing UniFi
objects must produce a no-change plan after import before any desired-state edit
is applied.
