"""Fixed trunk carrier checks; no native VLAN or forwarding qualification."""

import re

import port_description as evidence

HEADER = "Port Link State Dupl Speed Trunk Tag Pvid Pri MAC Name"
PHYSICAL_PORTS = frozenset(
    (
        *(f"1/1/{number}" for number in range(1, 49)),
        *(f"1/2/{number}" for number in range(1, 11)),
        *(f"1/3/{number}" for number in range(1, 9)),
    )
)
EXPECTED_SPEEDS = {"1/2/2": "10G", "1/2/6": "40G", "1/3/1": "10G"}
MAC = r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"


def require_links(brief: str) -> None:
    """Require a complete unambiguous table and all three fixed carriers up."""
    if (
        not isinstance(brief, str)
        or not brief.isascii()
        or re.search(r"[^\x20-\x7e\r\n\t]", brief)
        or re.search(r"\r(?!\n)", brief)
    ):
        raise evidence.Rejected("trunk interface brief table required")
    physical: dict[str, list[str]] = {}
    virtual: set[str] = set()
    headers = 0
    for line in brief.splitlines():
        words = line.split()
        if not words:
            continue
        if " ".join(words) == HEADER:
            headers += 1
            continue
        if headers == 0 or len(words) < 10 or re.fullmatch(MAC, words[9]) is None:
            raise evidence.Rejected("trunk interface brief table shape")
        name = words[0]
        if name in PHYSICAL_PORTS:
            if name in physical:
                raise evidence.Rejected("duplicate trunk physical port row")
            physical[name] = words
        elif name == "mgmt1" or re.fullmatch(r"ve[1-9][0-9]*", name):
            if name in virtual:
                raise evidence.Rejected("duplicate trunk virtual interface row")
            virtual.add(name)
        else:
            raise evidence.Rejected("unknown trunk interface brief row")
    if set(physical) != PHYSICAL_PORTS or "mgmt1" not in virtual:
        raise evidence.Rejected("incomplete trunk interface brief table")
    for name, speed in EXPECTED_SPEEDS.items():
        row = physical[name]
        if (
            len(row) != 10
            or row[1] != "Up"
            or row[3:5] != ["Full", speed]
            or row[2] not in ("Forward", "Blocked")
            or row[5] != "None"
            or row[6] not in ("Yes", "No")
            or not (row[7] == "N/A" or row[7].isdigit())
            or not row[8].isdigit()
        ):
            raise evidence.Rejected("fixed trunk carrier or speed required")
