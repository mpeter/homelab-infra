"""Fixed carrier admission regressions; carrier does not prove native VLAN state."""

import pytest

import port_description as evidence
import trunk_link_admission as engine


def brief() -> str:
    return "\n".join(
        (
            engine.HEADER,
            *(
                f"{port} Up Forward Full {engine.EXPECTED_SPEEDS[port]} None No 1 0 748e.f8e7.8d50"
                if port in engine.EXPECTED_SPEEDS
                else f"{port} Down None None None None No 1 0 748e.f8e7.8d50"
                for port in sorted(engine.PHYSICAL_PORTS)
            ),
            engine.HEADER,
            "mgmt1 Down None None None None No None 0 748e.f8e7.8d50",
            "ve1 Up N/A N/A N/A None N/A N/A N/A 748e.f8e7.8d50",
        )
    )


def test_complete_carriers_with_repeated_header() -> None:
    engine.require_links(brief())
    engine.require_links(brief().replace("None No 1", "None Yes N/A"))


@pytest.mark.parametrize("port", list(engine.EXPECTED_SPEEDS))
@pytest.mark.parametrize("change", ["down", "speed", "missing", "duplicate", "name"])
def test_fixed_ports_reject_bad_carrier_or_ambiguous_row(
    port: str, change: str
) -> None:
    lines = brief().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(port + " "))
    if change == "down":
        lines[index] = lines[index].replace("Up Forward Full", "Down None None")
    elif change == "speed":
        lines[index] = lines[index].replace(engine.EXPECTED_SPEEDS[port], "1G")
    elif change == "missing":
        lines.pop(index)
    elif change == "duplicate":
        lines.append(lines[index])
    else:
        lines[index] += " ambiguous name"
    with pytest.raises(evidence.Rejected):
        engine.require_links("\n".join(lines))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "brief",
        brief().removeprefix(engine.HEADER + "\n"),
        brief().replace("1/1/1 ", "2/1/1 "),
        brief().replace("mgmt1 ", "mgmt2 "),
        brief().replace("748e.f8e7.8d50", "bad-mac"),
        brief() + "\n% Error: incomplete",
        brief().replace("1/2/2 Up", "1/2/2 Unknown"),
        brief().replace("1/2/2 Up Forward", "1/2/2 Up Unknown"),
        brief().replace("1/2/2 Up Forward Full", "1/2/2 Up Forward Half"),
        brief() + "\nmgmt1 Down None None None None No None 0 748e.f8e7.8d50",
    ],
)
def test_table_shape_rejects_ambiguity(text: str) -> None:
    with pytest.raises(evidence.Rejected):
        engine.require_links(text)


def test_carrier_gate_does_not_assert_forwarding() -> None:
    engine.require_links(brief().replace("1/2/2 Up Forward", "1/2/2 Up Blocked"))
