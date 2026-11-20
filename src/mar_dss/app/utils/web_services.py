"""Helpers for calling public web services like OpenStreetMap.

On a server, all users requests come from the same address. So we send a
User-Agent that names the app, and send Nominatim at most one request a
second (usage policy: https://operations.osmfoundation.org/policies/nominatim/)
"""

import os
import threading
import time

import requests

from mar_dss import __version__

USER_AGENT = os.environ.get(
    "MAR_HTTP_USER_AGENT",
    f"MAR-Tool/{__version__} (+https://github.com/GSIEnvironmental/mar_tool)",
)

_NOMINATIM_MIN_INTERVAL_SECONDS = 1.0
_nominatim_lock = threading.Lock()
_nominatim_last_request = 0.0


def nominatim_get(url, timeout=20, **kwargs):
    """GET a Nominatim URL, waiting if needed so the app stays under one request a second."""
    global _nominatim_last_request
    with _nominatim_lock:
        wait = _nominatim_last_request + _NOMINATIM_MIN_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _nominatim_last_request = time.monotonic()
    headers = {**kwargs.pop("headers", {}), "User-Agent": USER_AGENT}
    return requests.get(url, headers=headers, timeout=timeout, **kwargs)
