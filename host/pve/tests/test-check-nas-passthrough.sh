#!/usr/bin/env bash
set -euo pipefail

checker=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/check-nas-passthrough.sh

expect_status() {
  local expected=$1
  shift
  local actual=0
  bash "$checker" validate "$@" >/dev/null 2>&1 || actual=$?
  [[ $actual == "$expected" ]] || {
    printf 'expected exit %s, got %s for %s\n' "$expected" "$actual" "$*" >&2
    exit 1
  }
}

expect_status 0 running vfio-pci $'rpool\nfast-vm'
expect_status 1 running mpt3sas $'rpool\nfast-vm'
expect_status 0 stopped vfio-pci $'rpool\nfast-vm'
expect_status 0 stopped mpt3sas $'rpool\nfast-vm'
expect_status 1 stopped other-driver $'rpool\nfast-vm'
expect_status 1 unknown vfio-pci $'rpool\nfast-vm'
expect_status 1 running vfio-pci $'rpool\nfast-vm\ntank'
expect_status 1 stopped mpt3sas $'rpool\nfast-vm\ntank'
expect_status 1 stopped mpt3sas $'rpool\nfast-vm\narray'

printf 'NAS passthrough state tests PASS\n'
