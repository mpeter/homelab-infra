# OpenTofu

This directory will contain Proxmox provider configuration, reusable VM and
container modules, and environment composition. It is intentionally empty until
the remote encrypted state backend and automation identity are established.

OpenTofu will own Proxmox resources, not configuration inside guests. Plans are
reviewed before apply, and existing resources are imported before management.
