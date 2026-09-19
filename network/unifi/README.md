# UniFi control plane

OpenTofu owns supported UniFi networks, WLANs, DHCP, DNS, and firewall policy.
AAP owns controller backup, health checks, workflow approvals, and orchestration
around plans and applies.

## Provider compatibility gate

The original
[`paultyng/unifi` provider](https://github.com/paultyng/terraform-provider-unifi)
is archived. Two candidates to test are the
[`BadgerOps/unifi` Integration API provider](https://registry.terraform.io/providers/BadgerOps/unifi/latest/docs)
and the
[`ubiquiti-community/unifi` provider](https://registry.terraform.io/providers/ubiquiti-community/unifi/latest/docs).
Before adding provider code:

1. Record the controller product, application version, network-device firmware,
   API capabilities, and authentication methods.
2. Compare a current Integration API provider with the active community fork
   for the specific objects this lab uses.
3. Use a dedicated least-privileged identity or API key and test only read
   operations.
4. Record the chosen provider, version, unsupported resources, and upgrade test
   in an ADR update.

## Import-first adoption

Create a dedicated UniFi root and state backend. Export the current object list,
map stable controller IDs to resource addresses, import one resource class at a
time, and reconcile configuration until `tofu plan` reports no changes. Review
any field that the API omits or normalizes before suppressing drift. Only then
make a bounded desired-state edit.

Keep controller backups independent of OpenTofu state. A syntactically valid
plan does not prove traffic policy: every firewall, VLAN, DHCP, DNS, or WLAN
change needs API read-back plus permitted and denied path tests.
