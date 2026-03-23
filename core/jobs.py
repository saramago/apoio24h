from __future__ import annotations

import threading
import time


class ProviderRefreshJobs:
    def __init__(self, providers: dict[str, object], interval_seconds: int) -> None:
        self.providers = providers
        self.interval_seconds = max(interval_seconds, 300)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def warmup(self) -> None:
        for provider in self.providers.values():
            provider.get_data(force_refresh=True)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.warmup()
            self._stop_event.wait(self.interval_seconds)
