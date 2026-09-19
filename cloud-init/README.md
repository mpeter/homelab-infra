# Guest bootstrap

Cloud-init data belongs here when it provides only the minimum first-boot state:
hostname, initial identity, SSH trust, networking, guest agent, and access needed
for AAP. Long-lived guest configuration belongs in Ansible.

OpenShift nodes use Ignition-generated installation assets rather than
cloud-init.
