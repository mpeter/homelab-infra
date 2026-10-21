"""Fixed VLAN read-back facts; synthetic after fixtures establish no live admission."""

from dataclasses import dataclass
import re

NAMES = {1: "DEFAULT-VLAN", 132: "DEFAULT-DECKPIN"}
LABELS = ("Untagged", "Tagged", "Uplink", "DualMode", "Mac-Vlan")
Port = tuple[int, int, int]


class Rejected(ValueError):
    """Reject incomplete or ambiguous read-back without echoing its contents."""


@dataclass(frozen=True)
class VlanMembership:
    vlan: int
    name: str
    untagged: tuple[Port, ...]
    tagged: tuple[Port, ...]
    uplink: tuple[Port, ...]
    dual_mode: tuple[Port, ...]
    mac_vlan: tuple[Port, ...]
    monitoring: str = "Disabled"
    spanning_tree: str = "On"


def parse_vlan(text: str, vlan: int) -> VlanMembership:
    """Parse every fixed firmware field; allow only ordered numeric row wrapping."""
    if (
        type(vlan) is not int
        or vlan not in NAMES
        or not isinstance(text, str)
        or not text.isascii()
        or re.search(r"[^\x20-\x7e\r\n]", text)
        or re.search(r"\r(?!\n)", text)
    ):
        raise Rejected("invalid fixed VLAN read-back")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = [
        "Total PORT-VLAN entries: 2",
        "Maximum PORT-VLAN entries: 64",
        "Legend: [Stk=Stack-Id, S=Slot]",
        f"PORT-VLAN {vlan}, Name {NAMES[vlan]}, Priority level0, Spanning tree On",
    ]
    if lines[:4] != header or lines[-1:] != ["Monitoring: Disabled"]:
        raise Rejected("VLAN headers or monitoring")
    groups: list[tuple[Port, ...]] = []
    cursor = 4
    for label in LABELS:
        ports: list[Port] = []
        seen = False
        none = False
        while cursor < len(lines) - 1 and lines[cursor].startswith(f"{label} Ports:"):
            line = lines[cursor]
            cursor += 1
            if line == f"{label} Ports: None":
                if seen:
                    raise Rejected("duplicate membership row")
                none = True
            else:
                match = re.fullmatch(
                    re.escape(label)
                    + r" Ports: \(U1/M([123])\) +([0-9]+(?: +[0-9]+)*)",
                    line,
                )
                if match is None or none:
                    raise Rejected("invalid membership row")
                slot = int(match.group(1))
                for number in match.group(2).split():
                    value = int(number)
                    port = (1, slot, value)
                    if (
                        number != str(value)
                        or not 1 <= value <= {1: 48, 2: 10, 3: 8}[slot]
                        or (ports and port <= ports[-1])
                    ):
                        raise Rejected("duplicate or unordered membership port")
                    ports.append(port)
            seen = True
        if not seen:
            raise Rejected("missing or unordered membership label")
        groups.append(tuple(ports))
    if cursor != len(lines) - 1:
        raise Rejected("unparsed VLAN read-back")
    return VlanMembership(
        vlan, NAMES[vlan], groups[0], groups[1], groups[2], groups[3], groups[4]
    )


def check_membership(
    vlan1_text: str, vlan132_text: str, *, phase: str
) -> dict[str, object]:
    """Check fixed before/after membership only; never admit an apply or save."""
    if phase not in ("before", "after"):
        raise Rejected("fixed before or after phase required")
    vlan1, vlan132 = parse_vlan(vlan1_text, 1), parse_vlan(vlan132_text, 132)
    default_ports = (
        *((1, 1, port) for port in range(1, 48)),
        *((1, 2, port) for port in range(1, 11) if phase == "after" or port != 6),
        *((1, 3, port) for port in range(1, 9)),
    )
    expected1 = VlanMembership(1, NAMES[1], default_ports, (), (), (), ())
    expected132 = VlanMembership(
        132,
        NAMES[132],
        ((1, 2, 6),) if phase == "before" else (),
        ((1, 1, 48),),
        (),
        (),
        (),
    )
    return {
        "scope": "fixed_vlan_membership_only",
        "phase": phase,
        "accepted": vlan1 == expected1 and vlan132 == expected132,
        "vlan1": vlan1,
        "vlan132": vlan132,
        "live_admission": False,
        "apply_enabled": False,
        "task_complete": False,
        "actual_forward_observed": False,
    }
