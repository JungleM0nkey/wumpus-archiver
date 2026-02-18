"""Concurrent process manager for running backend + frontend together."""

import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ManagedProcess:
    """A managed subprocess with label and color."""

    label: str
    cmd: list[str]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    process: asyncio.subprocess.Process | None = field(default=None, init=False)

    @property
    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self.process is not None and self.process.returncode is None


# ANSI color codes for distinguishing process output
_COLORS = {
    "backend": "\033[36m",   # cyan
    "frontend": "\033[35m",  # magenta
    "build": "\033[33m",     # yellow
}
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _prefix(label: str) -> str:
    """Return a colored prefix for log lines."""
    color = _COLORS.get(label, "\033[37m")
    return f"{color}{_BOLD}[{label}]{_RESET} "


async def _stream_output(
    stream: asyncio.StreamReader | None,
    label: str,
) -> None:
    """Read lines from a subprocess stream and print with a prefix."""
    if stream is None:
        return
    prefix = _prefix(label)
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        print(f"{prefix}{text}", flush=True)


async def _run_process(proc: ManagedProcess) -> int:
    """Start a managed process and stream its output.

    Args:
        proc: The process definition to run.

    Returns:
        Process exit code (0 on success).
    """
    merged_env = {**os.environ, **proc.env}

    proc.process = await asyncio.create_subprocess_exec(
        *proc.cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(proc.cwd) if proc.cwd else None,
        env=merged_env,
    )

    await _stream_output(proc.process.stdout, proc.label)
    return await proc.process.wait()


async def _terminate_process(proc: ManagedProcess) -> None:
    """Gracefully terminate a managed process."""
    if not proc.is_running or proc.process is None:
        return

    logger.debug("Terminating %s (pid=%s)", proc.label, proc.process.pid)

    try:
        proc.process.terminate()
        try:
            await asyncio.wait_for(proc.process.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning("Force-killing %s", proc.label)
            proc.process.kill()
            await proc.process.wait()
    except ProcessLookupError:
        pass  # already exited


async def run_concurrently(
    processes: list[ManagedProcess],
    *,
    stop_on_first_exit: bool = True,
) -> int:
    """Run multiple processes concurrently, streaming their output.

    Handles SIGINT/SIGTERM gracefully by terminating all children.

    Args:
        processes: List of processes to run.
        stop_on_first_exit: If True, terminate all when any process exits.

    Returns:
        Combined exit code (0 if all succeeded).
    """
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        print(f"\n{_prefix('system')}Shutting down...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    tasks = [asyncio.create_task(_run_process(p)) for p in processes]

    try:
        # Wait for either a signal or a process to exit
        done: set[asyncio.Task[int]] = set()
        pending: set[asyncio.Task[int]] = set(tasks)

        shutdown_task = asyncio.create_task(shutdown_event.wait())

        while pending and not shutdown_event.is_set():
            wait_set: set[asyncio.Task[int | bool]] = {*pending, shutdown_task}
            finished, _ = await asyncio.wait(
                wait_set,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in finished:
                if task is shutdown_task:
                    continue
                # A process has exited
                pending.discard(task)  # type: ignore[arg-type]
                done.add(task)  # type: ignore[arg-type]
                label = processes[tasks.index(task)].label  # type: ignore[arg-type]
                code = task.result()
                exit_msg = "exited cleanly" if code == 0 else f"exited with code {code}"
                print(f"{_prefix('system')}{label} {exit_msg}")

                if stop_on_first_exit:
                    shutdown_event.set()

    finally:
        # Clean up all processes
        for proc in processes:
            await _terminate_process(proc)

        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    # Return worst exit code
    codes = [t.result() for t in tasks if t.done() and not t.cancelled()]
    return max(codes) if codes else 1


async def run_and_wait(proc: ManagedProcess) -> int:
    """Run a single process to completion.

    Args:
        proc: The process to run.

    Returns:
        Process exit code.
    """
    return await _run_process(proc)


def resolve_portal_dir() -> Path:
    """Locate the portal directory relative to the package.

    Returns:
        Absolute path to the portal/ directory.

    Raises:
        FileNotFoundError: If portal directory cannot be found.
    """
    # Try relative to package source
    pkg_root = Path(__file__).parent.parent.parent.parent
    portal = pkg_root / "portal"
    if portal.exists() and (portal / "package.json").exists():
        return portal.resolve()

    # Try CWD
    cwd_portal = Path.cwd() / "portal"
    if cwd_portal.exists() and (cwd_portal / "package.json").exists():
        return cwd_portal.resolve()

    raise FileNotFoundError(
        "Cannot find portal/ directory. "
        "Run this command from the project root or ensure the portal is installed."
    )


def find_npm() -> str:
    """Find the npm executable path.

    Returns:
        Path to npm executable.

    Raises:
        FileNotFoundError: If npm is not installed.
    """
    import shutil

    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError(
            "npm not found. Install Node.js to use frontend features: "
            "https://nodejs.org/"
        )
    return npm
