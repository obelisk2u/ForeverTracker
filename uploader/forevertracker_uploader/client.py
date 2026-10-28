"""HTTP upload with retries for temporary failures only."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from forevertracker_uploader import __version__

RETRYABLE = {429, 500, 502, 503, 504}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class UploadError(Exception):
    def __init__(self, message: str, *, permanent: bool):
        self.permanent = permanent
        super().__init__(message)


def check_server_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return url.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS:
        return url.rstrip("/")
    raise ValueError("the server URL must use https:// (plain http is only allowed for localhost)")


@dataclass
class Uploader:
    server_url: str
    transport: httpx.BaseTransport | None = None
    attempts: int = 5
    base_delay: float = 1.0
    sleep: callable = time.sleep

    def __post_init__(self):
        self.server_url = check_server_url(self.server_url)
        self._client = httpx.Client(
            transport=self.transport,
            timeout=30.0,
            headers={"X-ForeverTracker-Client": f"uploader/{__version__}", "Content-Type": "application/json"},
        )

    def upload_batch(self, batch_json: bytes) -> dict:
        url = f"{self.server_url}/api/v1/ingest/batches"
        delay = self.base_delay
        last: str = ""
        for attempt in range(1, self.attempts + 1):
            try:
                res = self._client.post(url, content=batch_json)
            except httpx.TransportError as err:
                last = f"network error: {err}"
            else:
                if res.status_code == 200:
                    return res.json()
                if res.status_code not in RETRYABLE:
                    raise UploadError(f"server rejected the batch (HTTP {res.status_code}): {res.text[:300]}", permanent=True)
                last = f"HTTP {res.status_code}"
                retry_after = res.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, min(float(retry_after), 300.0))
            if attempt < self.attempts:
                self.sleep(delay)
                delay = min(delay * 2, 120.0)
        raise UploadError(f"gave up after {self.attempts} attempts ({last})", permanent=False)

    def close(self) -> None:
        self._client.close()
