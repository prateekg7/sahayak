"""Temporary container entry point until the application and worker exist."""

from __future__ import annotations

import signal
import sys
from threading import Event


def run(role: str) -> int:
    """Keep a bootstrap container alive until its dedicated runtime is added.

    Args:
        role: The container role, either ``app`` or ``worker``.

    Returns:
        A conventional process exit status.
    """
    if role not in {"app", "worker"}:
        print("container role must be app or worker", file=sys.stderr)
        return 2

    if role == "worker":
        from sahayak.worker import main as worker_main

        return worker_main()

    stop_requested = Event()

    def request_stop(_signal_number: int, _frame: object) -> None:
        stop_requested.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    print(f"sahayak {role} bootstrap is running", flush=True)
    stop_requested.wait()
    return 0


def main() -> int:
    """Run the role supplied as the sole command-line argument."""
    if len(sys.argv) != 2:
        print("usage: python -m sahayak.container <app|worker>", file=sys.stderr)
        return 2
    return run(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
