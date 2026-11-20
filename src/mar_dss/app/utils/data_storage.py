"""
Keeps each user's project data separate.

Each browser gets a cookie with a random session id, and its data is kept in
memory under that id. Code that runs outside a web request (startup, tests,
scripts) uses one shared dictionary, and each new session starts from a copy
of it.

Because the data lives in memory, run the app as a single process (threads
are fine). Sessions idle for more than MAR_SESSION_TTL_HOURS (default 12) are
dropped, and at most MAR_MAX_SESSIONS (default 500) are kept at once.
"""

import copy
import os
import secrets
import threading
import time

# g is Flask's scratch space for one request. We keep the session id on it.
from flask import g, has_request_context, request

# Name of the session cookie, how long an idle session lasts, and how many
# sessions to keep. The last two can be set in compose.prod.yaml.
SESSION_COOKIE = "mar_session"
_SESSION_TTL_SECONDS = float(os.environ.get("MAR_SESSION_TTL_HOURS", "12")) * 3600
_MAX_SESSIONS = int(os.environ.get("MAR_MAX_SESSIONS", "500"))

# Used outside a request, and copied for each new session.
_data_storage = {}

# session id -> {"data": dict, "last_seen": float}
_sessions = {}
_sessions_lock = threading.Lock()


def _evict_sessions(now):
    """Drop expired sessions, then the oldest ones if we're at the limit."""
    expired = [sid for sid, entry in _sessions.items() if now - entry["last_seen"] > _SESSION_TTL_SECONDS]
    for sid in expired:
        del _sessions[sid]
    overflow = len(_sessions) - _MAX_SESSIONS + 1
    if overflow > 0:
        for sid in sorted(_sessions, key=lambda s: _sessions[s]["last_seen"])[:overflow]:
            del _sessions[sid]


def _current_storage():
    """Return the current browser's data."""
    if not has_request_context():
        return _data_storage
    sid = getattr(g, "mar_session_id", None)
    if sid is None:
        # No session (init_app wasn't called), so act like the desktop app.
        return _data_storage
    now = time.time()
    with _sessions_lock:
        entry = _sessions.get(sid)
        if entry is None:
            _evict_sessions(now)
            entry = {"data": copy.deepcopy(_data_storage), "last_seen": now}
            _sessions[sid] = entry
        entry["last_seen"] = now
        return entry["data"]


def init_app(server):
    """Set up session cookies on the Flask server."""
    secure = os.environ.get("MAR_COOKIE_SECURE", "0") == "1"
    # Only send the cookie to this app, not to other apps on the same host.
    path = os.environ.get("DASH_REQUESTS_PATHNAME_PREFIX", "/")

    @server.before_request
    def _assign_session_id():
        """Before each request, read the browser's session id from its cookie.

        A browser with no cookie (or a bad one) gets a new random id.
        """
        sid = request.cookies.get(SESSION_COOKIE)
        if not sid or len(sid) > 64:
            sid = secrets.token_urlsafe(32)
            g.mar_new_session = True
        g.mar_session_id = sid

    @server.after_request
    def _set_session_cookie(response):
        """After each request, send the cookie back if the session id is new."""
        if getattr(g, "mar_new_session", False):
            response.set_cookie(
                SESSION_COOKIE,
                g.mar_session_id,
                httponly=True,
                samesite="Lax",
                secure=secure,
                path=path,
            )
        return response


def get_data(key):
    """Get one value from the current session's storage."""
    return _current_storage().get(key)


def set_data(key, value):
    """Set one value in the current session's storage."""
    _current_storage()[key] = value


def clear_data():
    """Clear all data from the current session's storage."""
    _current_storage().clear()


def get_data_storage():
    """Get the current session's whole storage dictionary."""
    return _current_storage()
