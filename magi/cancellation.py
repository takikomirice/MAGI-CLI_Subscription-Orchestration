from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import threading


@dataclass(slots=True)
class RunCancellation:
    reason: str = "Cancelled by user."
    _event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _processes: dict[int, subprocess.Popen[str]] = field(default_factory=dict)

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> bool:
        if self._event.is_set():
            return False
        self._event.set()
        with self._lock:
            processes = list(self._processes.values())
        for process in processes:
            terminate_process_tree(process)
        return True

    def register_process(self, process: subprocess.Popen[str]) -> bool:
        with self._lock:
            if self._event.is_set():
                should_cancel = True
            else:
                self._processes[process.pid] = process
                should_cancel = False
        if should_cancel:
            terminate_process_tree(process)
            return False
        return True

    def unregister_process(self, process: subprocess.Popen[str] | None) -> None:
        if process is None:
            return
        with self._lock:
            self._processes.pop(process.pid, None)


def remove_history_file(project_root: Path) -> bool:
    history_path = project_root / ".magi_history"
    if not history_path.exists():
        return False
    history_path.unlink()
    return True


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
