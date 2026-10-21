from contextlib import contextmanager
import types
import time
from unittest.mock import patch

import pytest

import native_trunk_plan as plan
import port_description as evidence
import r8_current_observation as observer
from test_native_trunk_observation import operational, r8_fixture, tables
from test_port_description import VERSION


class Channel:
    def __init__(self, bodies):
        self.bodies = bodies
        self.chunks = [b"SSH@headwater>"]
        self.sent = []
        self.closed = False

    def sendall(self, value):
        self.sent.append(value)
        if value == "enable\r":
            self.chunks = [b"enable\r\nUser Name:"]
        elif value == "homelab_audit\r":
            self.chunks = [b"homelab_audit\r\nPassword:"]
        elif value == "A" * 32 + "\r":
            self.chunks = [b"\r\nSSH@headwater#"]
        else:
            command = value.removesuffix("\r")
            self.chunks = [
                f"{command}\r\n{self.bodies[command]}\r\nSSH@headwater#".encode()
            ]

    def recv_ready(self):
        return bool(self.chunks)

    def recv(self, size):
        return self.chunks.pop(0)


@pytest.fixture
def current_observation(tmp_path):
    pin = tmp_path / "known_hosts"
    pin.write_text("fixture")
    pin.chmod(0o600)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    config_lines = list(r8_fixture())
    config_lines.insert(1, "username homelab_audit privilege 5 password " + "A" * 32)
    config = tuple(config_lines)
    state = plan.State(
        tuple((vlan, tuple(sorted(plan.PORTS))) for vlan, _ in plan.VLANS),
        tuple(sorted(plan.PORTS)),
    )
    tables_by_vlan = tables(state)
    bodies = {
        "show version": VERSION,
        "show running-config": "\n".join(config),
        "show configuration": "\n".join(config),
        "show interfaces brief": operational(state),
        "show mac-address": "MAC-Address Port Type Index VLAN\nTotal active entries from all ports = 0",
        "show interfaces ethernet 1/1/47": "Port 1/1/47",
        **{f"show vlan {vlan}": body for vlan, body in tables_by_vlan.items()},
    }
    channel = Channel(bodies)
    sessions = []

    module = types.SimpleNamespace()

    @contextmanager
    def session(received_pin, capture_parent, *, user, payload, deadline=None):
        assert received_pin == pin
        assert user == "homelab_audit"
        assert payload["audit_password"] == "A" * 32
        capture_dir = capture_parent / "audit-capture"
        capture_dir.mkdir(mode=0o700)
        console = module.Console(channel, "A" * 32, capture_dir)
        console.deadline = deadline
        console.enable(username=user)
        sessions.append(console)
        try:
            yield console, payload
        finally:
            channel.closed = True

    module.session = session

    def load(name, path):
        assert name == "r8_current_observation_session"
        return module

    return pin, runtime, config, channel, sessions, load


def test_collects_exact_config_and_all_vlan_tables_in_one_audit_session(
    current_observation,
):
    pin, runtime, config, channel, sessions, load = current_observation

    def provider():
        return "A" * 32

    with patch.object(observer.base, "_load", side_effect=load):
        payload = observer.observe(pin, runtime, config, provider)

    running, startup = evidence.evidence_config(payload, observer.base.PORT)
    assert running == startup == config
    assert payload["r8_vlan_commands"] == list(observer.COMMANDS)
    assert set(payload["r8_vlan_tables"]) == {"1", "10", "20", "30", "40", "132"}
    assert set(payload["r8_vlan_capture_sha256"]) == set(observer.COMMANDS)
    assert payload["r8_vlan_raw_capture_sha256"]
    assert payload["observation_source_sha256"] == observer.SOURCE_SHA256
    assert len(sessions) == 1
    assert channel.sent[3:] == [
        command + "\r" for command in (*observer.base.COMMANDS, *observer.COMMANDS)
    ]


def test_absolute_deadline_reaches_the_audit_session_setup(current_observation):
    pin, runtime, config, _, sessions, load = current_observation
    deadline = time.monotonic() + 30

    with patch.object(observer.base, "_load", side_effect=load):
        observer.observe(pin, runtime, config, lambda: "A" * 32, deadline=deadline)

    assert sessions[0].deadline == deadline


def test_rejects_startup_drift_before_returning_observation(current_observation):
    pin, runtime, config, _, _, load = current_observation
    different = (*config[:-1], "hostname changed", config[-1])
    with patch.object(observer.base, "_load", side_effect=load):
        with pytest.raises(observer.Rejected, match="startup differs"):
            observer.observe(pin, runtime, different, lambda: "A" * 32)


def test_returns_unsaved_running_state_while_pinning_startup(current_observation):
    pin, runtime, config, channel, _, load = current_observation
    running = (*config[:-1], "hostname temporary", config[-1])
    channel.bodies["show running-config"] = "\n".join(running)

    with patch.object(observer.base, "_load", side_effect=load):
        payload = observer.observe(pin, runtime, config, lambda: "A" * 32)

    observed_running, observed_startup = evidence.evidence_config(
        payload, observer.base.PORT
    )
    assert observed_running == running
    assert observed_startup == config
