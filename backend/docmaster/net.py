"""Network policy. The backend opens exactly one kind of connection: IMAP to the user's own mail
server, and only when the user asks for a mailbox draft. `offline_mode` makes even that
impossible. `check_reachability` helps diagnose VPN/firewall situations without sending credentials."""
from __future__ import annotations
import socket, ssl, time
from .errors import DocMasterError


class OfflineMode(DocMasterError):
    code, rpc_code, user_message = "OFFLINE_MODE", -32080, "Offline mode is on: the app will not connect to any server. Turn it off in Settings → Privacy to save drafts to your mailbox."


def check_reachability(host: str, port: int, timeout: float = 8.0) -> dict:
    """DNS → TCP → TLS handshake, no login. Each stage reports separately so VPN/DNS problems are obvious."""
    out = {"host": host, "port": port, "dns": None, "tcp": None, "tls": None, "ms": None, "ok": False}
    t0 = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        out["dns"] = {"ok": True, "addresses": sorted({i[4][0] for i in infos})[:4]}
    except socket.gaierror as e:
        out["dns"] = {"ok": False, "error": f"DNS lookup failed ({e.errno})"}
        return out
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            out["tcp"] = {"ok": True}
            try:
                with ssl.create_default_context().wrap_socket(s, server_hostname=host) as tls:
                    cert = tls.getpeercert() or {}
                    out["tls"] = {"ok": True, "protocol": tls.version(), "subject": dict(x[0] for x in cert.get("subject", ())).get("commonName")}
            except ssl.SSLError as e:
                out["tls"] = {"ok": False, "error": str(e)[:160]}
                return out
    except (OSError, socket.timeout) as e:
        out["tcp"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}
        return out
    out["ms"] = int((time.monotonic() - t0) * 1000); out["ok"] = True
    return out


def outbound_destinations(settings_all: dict) -> list[dict]:
    """Everything this app could ever connect to. Used by the Privacy screen."""
    acct = settings_all.get("imap_account")
    dests = []
    if acct:
        dests.append({"purpose": "Save email drafts to your mailbox (IMAP over TLS)", "host": acct["host"], "port": acct["port"], "when": "only when you click Create draft"})
    return dests


# ---------------------------------------------------------------------------------------------
# Process-wide guard: while offline mode is on, *no* outgoing TCP connection can be opened from
# this process, whatever code asks for it. The IMAP module checks the setting first and gives a
# friendly error; this guard is the backstop for everything else (new code, third-party libs).
# ---------------------------------------------------------------------------------------------
_is_offline = lambda: True          # replaced by install_guard
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and _is_offline():
        raise OfflineMode()
    return _orig_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and _is_offline():
        raise OfflineMode()
    return _orig_connect_ex(self, address)


def install_guard(is_offline) -> None:
    """is_offline: zero-arg callable returning the current offline_mode setting."""
    global _is_offline
    _is_offline = is_offline
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex


def uninstall_guard() -> None:
    socket.socket.connect = _orig_connect
    socket.socket.connect_ex = _orig_connect_ex
