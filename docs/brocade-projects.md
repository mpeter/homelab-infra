# Brocade ICX homelab projects

These projects combine the long-running ServeTheHome and Fohdeesha ICX community
work with the R720, Proxmox, AAP, and OpenShift design in this repository. Every
feature is conditional on live model, module, firmware, and license inventory.

## Why the switch is interesting

The community uses retired ICX hardware as much more than a dense access switch:

- a line-rate Layer 3 core between trusted VLANs;
- a low-cost 10/40 GbE server and storage fabric;
- a PoE power controller for access points, cameras, phones, and small nodes;
- a routing lab for OSPF, BGP, VRFs, VRRP, ACLs, and policy routing;
- a telemetry source for SNMP, sFlow, syslog, optical diagnostics, and packet
  mirroring;
- an enterprise CLI and automation target with real configuration and recovery
  behavior.

The live inventory identifies the switch as an ICX6610-48P running FastIron
08.0.30t. The rear module currently has native 40 GbE links up on `1/2/1` and
`1/2/6`, 10 GbE breakout lanes up on `1/2/2` through `1/2/5`, and the second
breakout group down. Port `1/3/1` is the active 10 GbE LAN uplink based on the
downstream MAC table. The reported R720 cable is on `1/2/2`, but the server's
interface identity has not yet been verified from both ends.

The switch also has a still-live VLAN 132: `1/1/48` is tagged and native 40 GbE
port `1/2/6` is untagged. Do not reuse either port until that network and its
far-end device are identified.

## Captured baseline

The initial read-only discovery and configuration backup are complete. Repeat
these commands before a change window to detect drift:

```text
show version
show chassis
show module
show license
show stack
show running-config
show interfaces brief
show interfaces ethernet 1/2/2
show statistics ethernet 1/2/2
show inline power
show optic
```

Record which image is primary and secondary, the boot monitor version, module
map, temperature and fan state, power supplies, licenses, optic/DAC identity,
link speed, VLAN membership, LAGs, and stack configuration. Back up both running
and startup configuration before writes.

The 2026-09-19 baseline found:

- FastIron 08.0.30u running from secondary flash with 08.0.30t preserved in
  primary flash for rollback;
- active 10G port-on-demand, advanced Layer 3, and MACsec licenses;
- identical running and startup configurations captured outside the public repo;
- NTPv4 client synchronization through VE 1 using independent Cloudflare and
  Google sources; NTP server mode is disabled;
- confirmed PoE controller hardware failure after build-004 programming was
  rejected under both FastIron 08.0.30t and 08.0.30u;
- Telnet and plaintext HTTP enabled, no HTTPS or SNMP listener, and SSH limited
  to obsolete algorithms;
- no observed Layer 3 forwarding traffic.

## Recommended projects

### 1. Instrument the physical network

Start with SNMPv3, syslog, interface counters, temperature, fan and PSU state,
PoE draw, and optical diagnostics. Send metrics to a small monitoring VM and
build Grafana views for utilization, errors, discards, link flaps, temperature,
and power. Add sFlow later if the live model and firmware support it reliably.

This has low operational risk and gives every later network experiment a
measurement baseline. AAP should collect a periodic configuration backup and a
daily read-only health artifact.

### 2. Make the R720 a measured 40 GbE endpoint

Use one of the native 40 GbE ports only after identifying its current peer and
VLAN role. Port `1/2/2` is a 10 GbE breakout lane, so it cannot be used as a
single 40 GbE endpoint. A future 40 GbE Proxmox or storage link needs `1/2/1` or
`1/2/6` plus a compatible NIC and cable. Keep the existing management path until
link, MTU, VLAN, reboot, and throughput tests pass.

Use `iperf3` between separate guests or a future NAS to measure the complete
path. A single flow may be limited by guest CPU, storage, NUMA placement, or the
virtual network before it reaches line rate. Jumbo frames are a later end-to-end
experiment, not a prerequisite.

### 3. Use QSFP breakout as a compact 10 GbE fan-out

The live rear module exposes two four-lane 10 GbE breakout groups. Lanes
`1/2/2` through `1/2/5` are up; `1/2/7` through `1/2/10` are available after
their cabling and intended VLAN are confirmed. This provides server fan-out
without consuming the front SFP+ bank.

### 4. Peer OpenShift with the physical network using BGP

The strongest Red Hat lab project is to peer an isolated OpenShift MetalLB or
FRR-K8s test with the ICX and advertise a small LoadBalancer prefix. This makes
OpenShift services routable without static per-service routes and exercises
BGP, route policy, failure detection, and cluster observability.

Begin in a dedicated lab VRF or VLAN with a reserved prefix and explicit prefix
filters. Do not advertise the pod, service, management, or default routes. The
exact OpenShift release and ICX BGP support must be verified before design.

### 5. Build a line-rate east-west Layer 3 core

Move selected trusted high-volume VLAN routing from the UniFi gateway to ICX
virtual interfaces so storage, development, and lab traffic can route at switch
speed. Keep WAN routing, NAT, VPN, and internet-edge policy on UniFi.

This change removes traffic from UniFi inspection and firewall paths. Start
with a disposable lab pair, add explicit ICX ACLs, and test permitted and denied
paths before considering development or storage networks.

### 6. Create a routing and segmentation playground

Use disposable VLANs and FRR VMs to learn OSPF, BGP, VRRP, policy routing, GRE,
and model-dependent VRF behavior. This is a better use of advanced Layer 3
features than placing the household network behind an experiment. AAP can
create a scenario, verify routes and reachability, then return the switch to the
known baseline.

### 7. Turn PoE into an automation actuator

On a PoE model, AAP can inventory draw and perform approved power cycles for an
access point, camera, phone, Raspberry Pi, or other standards-compliant device.
Useful workflows include recovering a failed AP, scheduling a disposable edge
lab, or alerting when a device's draw changes unexpectedly.

Disable legacy passive-power detection where the model guidance recommends it.
Every write workflow must identify the port by both switch interface and LLDP or
inventory evidence so the wrong device is not power-cycled.

### 8. Feed a network-security lab

Mirror a lab VLAN or selected server port to a Zeek, Suricata, or Security Onion
sensor. Combine that packet view with sFlow, syslog, and OpenShift Network
Observability to compare physical, hypervisor, and cluster visibility. Mirror
only bounded lab traffic so the sensor and mirror destination are not silently
oversubscribed.

### 9. Test MACsec and encrypted server links

Some licensed ICX6610 configurations support line-rate MACsec on the front
SFP+ ports. If the live hardware and peer NIC support a compatible mode, this
can become a useful Layer 2 encryption lab. Treat it as an isolated experiment;
interoperability and key management matter more than the feature checkbox.

### 10. Add a second ICX as a stacking and failure lab

A matching used switch can exercise high-speed stacking, configuration
synchronization, link failure, and maintenance procedures. A stack improves port
and link options but remains one logical control plane and does not make the
single R720 highly available.

## Suggested order

| Stage | Project | Risk | Evidence to advance |
|---:|---|---|---|
| 1 | Inventory, backup, SNMP, syslog, optical monitoring | Low | Complete inventory and enough clean telemetry to establish a baseline |
| 2 | Validate the existing high-speed R720 link | Low | Stable reboots, VLAN tests, error-free counters, throughput baseline |
| 3 | Configuration backup and bounded AAP workflows | Medium | Preview, apply, read-back, and rollback demonstrated on an unused port |
| 4 | sFlow and packet-mirror security lab | Low to medium | Collector capacity and mirror-loss behavior measured |
| 5 | OpenShift MetalLB/FRR-K8s BGP lab | Medium | Prefix filters, session recovery, and withdrawal tested |
| 6 | ICX Layer 3 routing and ACL lab | Medium | Permitted and denied paths verified with rollback |
| 7 | PoE power workflows, MACsec, or stacking | Feature-specific | Exact model support and physical recovery path proven |

## Constraints and cautions

- ICX6xxx management crypto is old. Put management on an isolated network and
  scope legacy SSH algorithms to a dedicated bastion or execution environment;
  do not enable them globally on administrator systems.
- The live switch currently exposes Telnet and plaintext HTTP, provides no
  HTTPS listener, and offers only legacy SSH key exchange and host-key
  algorithms. Disable Telnet and HTTP only after key-based SSH, console access,
  configuration backup, and rollback have been tested.
- `write memory` is required to make FastIron changes survive reboot. Runtime
  read-back and startup configuration must both be verified.
- Keep NTP client synchronization and source selection in the health checks so
  logs and automation retain reliable timestamps.
- Treat PoE as unavailable on this chassis; [the PoE RCA](brocade-poe-rca.md)
  records the failed controller recovery and hardware conclusion.
- Model, firmware, licenses, and module population change the feature set. The
  feature matrix is authoritative after live inventory.
- Moving routing into ICX can bypass UniFi policy and visibility.
- Older high-density models can be loud and power hungry. Measure idle power,
  temperature, and acoustics before adding a second switch.
- Community guides include unofficial license and hardware modification
  procedures. This repository does not automate identity, EEPROM, serial, or
  license manipulation.

## Research references

- [NYC Mesh Brocade Router CLI Notes](https://wiki.nycmesh.net/books/5-networking/page/brocade-router-cli-notes/revisions/902)
- [Fohdeesha FCX and ICX6610 guide](https://fohdeesha.com/docs/fcx.html)
- [Fohdeesha ICX6xxx advanced configuration](https://fohdeesha.com/docs/icx6xxx-adv.html)
- [Fohdeesha documentation index](https://fohdeesha.com/docs/index.html)
- [ServeTheHome Brocade ICX community thread](https://forums.servethehome.com/index.php?threads/brocade-icx-series-cheap-powerful-10gbe-40gbe-switching.21107/)
- [OpenShift BGP routing with FRR-K8s](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html-single/advanced_networking/)
