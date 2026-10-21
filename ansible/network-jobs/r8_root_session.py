"""Expose the pinned root SSH console to the fixed R8 native-trunk runner."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sys
from typing import Any

import writer_account
import r8_probe_runner

SOURCE = Path(__file__).resolve()
SOURCE_SHA256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def unchanged_sources() -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise writer_account.Rejected("R8 root session source drift")
    writer_account.unchanged_sources()


class RootConsole:
    """The narrow console contract consumed by the R8 transport."""

    def __init__(self, console: Any, runtime: Path):
        self.channel = console.channel
        self.runtime = runtime
        self._console = console

    def save(self, raw: str) -> None:
        self._console.save(raw)


@contextmanager
def root_console_session(
    pin: Path,
    runtime: Path,
    credential_provider: Callable[[], str],
    deadline: float | None = None,
) -> Iterator[RootConsole]:
    """Open one pinned root session; the caller owns admission and recovery."""
    unchanged_sources()
    if deadline is None:
        session = writer_account.account_session(pin, runtime, credential_provider)
    else:
        session = writer_account.account_session(
            pin, runtime, credential_provider, deadline=deadline
        )
    with session as account:
        unchanged_sources()
        console = getattr(account, "_console", None)
        if (
            console is None
            or not hasattr(console, "channel")
            or not hasattr(console, "save")
        ):
            raise writer_account.Rejected("pinned root console unavailable")
        yield RootConsole(console, runtime)


def run_full_trunk_candidate(
    guarded: Any,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
    held_guest_proof: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    guest_policy: dict[str, Any],
    recovery_observe: Callable[[RootConsole], Callable[[], dict[str, Any]]],
    pin: Path,
    runtime: Path,
    credential_provider: Callable[[], str],
    operation_budget: Any = None,
) -> dict[str, object]:
    """Run R8 with a pinned writer session and a separate recovery session."""
    unchanged_sources()
    if operation_budget is not None:
        operation_budget.check()

    def guarded_admit() -> None:
        unchanged_sources()
        if operation_budget is not None:
            operation_budget.check()
        admit()
        unchanged_sources()
        if operation_budget is not None:
            operation_budget.check()

    initial_session_deadline = (
        operation_budget.observation_deadline
        if operation_budget is not None
        else None
    )
    if initial_session_deadline is None:
        initial_session = root_console_session(pin, runtime, credential_provider)
    else:
        initial_session = root_console_session(
            pin,
            runtime,
            credential_provider,
            deadline=initial_session_deadline,
        )
    with initial_session as console:
        if operation_budget is not None:
            operation_budget.check()

        def open_recovery() -> tuple[
            Callable[[], dict[str, Any]], RootConsole, Callable[[], None]
        ]:
            if operation_budget is not None:
                operation_budget.check()
            recovery_deadline = (
                operation_budget.observation_deadline
                if operation_budget is not None
                else None
            )
            if recovery_deadline is None:
                session = root_console_session(pin, runtime, credential_provider)
            else:
                session = root_console_session(
                    pin,
                    runtime,
                    credential_provider,
                    deadline=recovery_deadline,
                )
            recovery_console = session.__enter__()
            try:
                unchanged_sources()
                if operation_budget is not None:
                    operation_budget.check()
                observe_recovery = recovery_observe(recovery_console)
                if not callable(observe_recovery):
                    raise writer_account.Rejected("fresh recovery observer required")
            except BaseException:
                session.__exit__(*sys.exc_info())
                raise

            def close_recovery() -> None:
                session.__exit__(None, None, None)
                if operation_budget is not None:
                    operation_budget.check()

            return observe_recovery, recovery_console, close_recovery

        result = r8_probe_runner.run_and_admit_full_trunk(
            guarded,
            baseline,
            observe,
            console,
            guarded_admit,
            binding,
            held_guest_proof,
            guest_policy,
            open_recovery,
            operation_budget,
        )
    return result
