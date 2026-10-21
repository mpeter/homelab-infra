"""Injected R8 guest-proof adapter; no collection, delivery or live action defaults.

Dependencies must honor the monotonic deadline and stop's two-second bound.
The adapter checks overruns but cannot preempt a blocking injected operation.
A returned status of passed means collection completed; semantic acceptance remains
with the parent's source-pinned r8_guest_acceptance policy and trusted parsers.
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
import inspect
import json
import re
import time
from typing import Any, Protocol, cast

import r8_guest_acceptance as acceptance
import r8_guest_generator


class Generator(Protocol):
    """One bounded stimulus lifecycle, including cleanup after failed start."""

    def start(self, deadline: float) -> None: ...
    def readiness(self, deadline: float) -> dict[str, Any]: ...
    def active(self, deadline: float) -> bool: ...
    def hold(self, deadline: float, start: float, offsets: list[float]) -> None: ...
    def finish(self, deadline: float) -> dict[str, Any]: ...
    def stop(self, timeout: float) -> Any: ...


@dataclass(frozen=True)
class Collectors:
    """Current-source dependencies receive the same finite deadline."""

    sources: Callable[[float], dict[str, str]]
    host: Callable[[float], dict[str, Any]]
    vm: Callable[[float], dict[str, Any]]
    management: Callable[[float], dict[str, Any]]
    nas: Callable[[float], dict[str, Any]]
    fedora: Callable[[float], tuple[dict[str, Any], dict[str, Any]]]
    switch: Callable[[float], dict[str, Any]]


def _snapshot(value: Any) -> Any:
    return json.loads(acceptance.canonical(value))


def _binding(held: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    acceptance.require(
        type(binding) is dict and set(binding) == acceptance.BINDING_FIELDS,
        "exact R8 callback binding required",
    )
    acceptance.require(
        type(binding["forward_count"]) is int
        and binding["forward_count"] == len(acceptance.trunk_plan.R8_FULL_FORWARD)
        and all(
            type(binding[key]) is str
            and re.fullmatch(r"[0-9a-f]{64}", binding[key]) is not None
            for key in acceptance.BINDING_FIELDS - {"forward_count"}
        ),
        "R8 callback identity/count required",
    )
    acceptance.require(
        type(held) is dict
        and acceptance.digest(held) == binding["boundary_observation_sha256"],
        "R8 held observation binding differs",
    )
    return cast(dict[str, Any], _snapshot(binding))


def _activity(
    result: dict[str, Any], fedora: dict[str, Any], window: dict[str, Any]
) -> dict[str, Any]:
    start, end = window["inner_interval"]
    lower, upper = window["clock_offset_bounds"]
    route = fedora["result"]["gateway_route"]
    acceptance.require(
        route["exit"] == 0 and route["stderr"] == "", "gateway route read failed"
    )
    gateway = json.loads(route["stdout"])[0]["dst"]
    terminal = result["terminal"]
    acceptance.require(
        result["status"] in {"passed", "failed"}
        and terminal["stdout_truncated"] is False
        and terminal["stderr_truncated"] is False
        and type(terminal["stdout_base64"]) is str
        and len(terminal["stdout_base64"]) <= 43692,
        "bounded generator terminal evidence required",
    )
    raw = base64.b64decode(terminal["stdout_base64"], validate=True)
    acceptance.require(len(raw) <= 32768, "generator output exceeds bound")
    pattern = (
        rb"(?m)^\[([0-9]+\.[0-9]+)\] 64 bytes from "
        + re.escape(gateway.encode("ascii"))
        + rb": icmp_seq=([0-9]+) ttl=[0-9]+ time=((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)) ms$"
    )
    replies = [
        match
        for match in re.finditer(pattern, raw)
        if start <= float(match[1]) + lower and float(match[1]) + upper <= end
    ]
    return {
        "successful_replies_in_window": len(replies),
        "window_seconds": end - start,
        "nic5_inner_interval": [start, end],
        "guest_to_workstation_offset_bounds": [lower, upper],
        "exit_zero_required": False,
    }


@dataclass(frozen=True)
class Producer:
    """Callback adapter; dependencies and source closure are selected by the parent."""

    collectors: Collectors
    generator: Generator
    monotonic: Callable[[], float] = time.monotonic
    epoch: Callable[[], float] = time.time

    @classmethod
    def with_fixed_generator(
        cls,
        collectors: Collectors,
        monotonic: Callable[[], float] = time.monotonic,
        epoch: Callable[[], float] = time.time,
    ) -> "Producer":
        """Bind fixed Fedora collectors and traffic to the source-pinned runner."""
        return cls(
            replace(collectors, fedora=r8_guest_generator.collect_network),
            r8_guest_generator.FiniteGuestGenerator(),
            monotonic,
            epoch,
        )

    def __call__(
        self,
        held: dict[str, Any],
        proof_binding: dict[str, Any],
        deadline: float | None = None,
    ) -> dict[str, Any]:
        deadline = min(
            self.monotonic() + 210,
            deadline if deadline is not None else float("inf"),
        )

        def invoke(function: Callable[..., Any], *args: Any) -> Any:
            if self.monotonic() >= deadline:
                raise TimeoutError("R8 guest collection deadline expired")
            result = function(deadline, *args)
            if self.monotonic() >= deadline:
                raise TimeoutError("R8 guest dependency exceeded deadline")
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("R8 guest dependencies must be synchronous")
            return result

        started = False
        try:
            binding = _binding(held, proof_binding)
            sources = _snapshot(invoke(self.collectors.sources))
            acceptance.require(
                type(sources) is dict
                and bool(sources)
                and all(
                    type(key) is str
                    and bool(key)
                    and type(value) is str
                    and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                    for key, value in sources.items()
                ),
                "current guest source closure required",
            )
            ready_request = self.epoch()

            def start_generator(deadline: float) -> None:
                nonlocal started
                started = True
                return self.generator.start(deadline)

            acceptance.require(
                invoke(start_generator) is None,
                "generator start must complete synchronously",
            )
            ready = invoke(self.generator.readiness)
            ready_response = self.epoch()
            stamp = datetime.fromisoformat(ready["observed_at"].replace("Z", "+00:00"))
            acceptance.require(stamp.tzinfo is not None, "readiness timezone required")
            offsets = [
                ready_request - stamp.timestamp(),
                ready_response - stamp.timestamp(),
            ]
            facts = {
                "host_before": _snapshot(invoke(self.collectors.host)),
                "vm_before": _snapshot(invoke(self.collectors.vm)),
            }
            start = self.epoch()
            acceptance.require(
                invoke(self.generator.active) is True, "stimulus not active"
            )
            facts["management"] = _snapshot(invoke(self.collectors.management))
            facts["nas"] = _snapshot(invoke(self.collectors.nas))
            fedora, dns = invoke(self.collectors.fedora)
            facts["fedora"], facts["dns"] = _snapshot(fedora), _snapshot(dns)
            facts["switch"] = _snapshot(invoke(self.collectors.switch))
            acceptance.require(
                invoke(self.generator.hold, start, offsets) is None,
                "generator hold must complete synchronously",
            )
            end = self.epoch()
            acceptance.require(
                invoke(self.generator.active) is True, "stimulus ended early"
            )
            facts["host_after"] = _snapshot(invoke(self.collectors.host))
            facts["vm_after"] = _snapshot(invoke(self.collectors.vm))
            facts["generator"] = _snapshot(invoke(self.generator.finish))
            facts["window"] = {
                "inner_interval": [start, end],
                "clock_offset_bounds": offsets,
            }
            facts["activity"] = _activity(
                facts["generator"], facts["fedora"], facts["window"]
            )
            acceptance.require(
                _snapshot(invoke(self.collectors.sources)) == sources,
                "guest source drift during held proof",
            )
            acceptance.require(
                _binding(held, proof_binding) == binding, "callback binding drift"
            )
            proof = {
                **binding,
                **facts,
                "kind": "read-only-active40g",
                "sources": sources,
                "selector_used": False,
                "status": "passed",
                "receipts": {
                    key: acceptance.digest(facts[key]) for key in acceptance.FACT_FIELDS
                },
            }
            acceptance.require(
                len(acceptance.canonical(proof)) <= 65536, "guest proof exceeds bound"
            )
        finally:
            if started:
                cleanup_start = self.monotonic()
                cleanup_result = self.generator.stop(2)
                if inspect.isawaitable(cleanup_result):
                    if inspect.iscoroutine(cleanup_result):
                        cleanup_result.close()
                    raise TypeError("R8 generator cleanup must complete synchronously")
                acceptance.require(
                    cleanup_result is None, "R8 generator cleanup result must be None"
                )
                if self.monotonic() - cleanup_start > 2:
                    raise TimeoutError("R8 generator cleanup exceeded two seconds")
        return proof
