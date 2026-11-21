"""JSON-RPC 2.0 over stdin/stdout, newline-delimited.

* one line per message; requests are dispatched to a small thread pool so a long conversion
  never blocks `system.ping`
* writes are serialised by a lock; stdout carries protocol only (logs go to stderr)
* server → client notifications (`job.progress`) are plain JSON-RPC notifications
* EOF on stdin or `system.shutdown` ends the loop after in-flight requests finish
"""
from __future__ import annotations
import json, logging, sys, threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from ..errors import DocMasterError

log = logging.getLogger("docmaster.rpc")
MAX_LINE = 8 * 1024 * 1024


def json_default(o):
    """YAML gives `date`/`datetime` for unquoted dates; paths and sets appear in diagnostics."""
    import datetime, pathlib
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    if isinstance(o, pathlib.PurePath):
        return str(o)
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


class Context:
    def __init__(self, server: "Server", request_id):
        self.server, self.request_id = server, request_id

    def progress(self, **params):
        self.server.notify("job.progress", params)


class Server:
    def __init__(self, methods: dict[str, Callable[..., Any]], inp=None, out=None, workers: int = 4):
        self.methods = methods
        self.inp = inp or sys.stdin
        self.out = out or sys.stdout
        self._wlock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rpc")
        self.stop = threading.Event()

    # ---- transport ----
    def send(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=json_default)
        with self._wlock:
            self.out.write(line + "\n"); self.out.flush()

    def notify(self, method: str, params: dict) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def _error(self, rid, code, message, data=None):
        err = {"code": code, "message": message}
        if data is not None: err["data"] = data
        self.send({"jsonrpc": "2.0", "id": rid, "error": err})

    # ---- loop ----
    def serve_forever(self) -> None:
        log.info("rpc server ready")
        for line in self.inp:
            if self.stop.is_set():
                break
            if len(line) > MAX_LINE:
                self._error(None, -32600, "request too large"); continue
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except ValueError:
                self._error(None, -32700, "parse error"); continue
            if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
                self._error(req.get("id") if isinstance(req, dict) else None, -32600, "invalid request"); continue
            if req["method"] == "system.shutdown":
                self.stop.set()
            self._pool.submit(self._handle, req)
        self._pool.shutdown(wait=True)
        log.info("rpc server stopped")

    def _handle(self, req: dict) -> None:
        rid, method, params = req.get("id"), req["method"], req.get("params") or {}
        fn = self.methods.get(method)
        if fn is None:
            return self._error(rid, -32601, f"method not found: {method}")
        if not isinstance(params, dict):
            return self._error(rid, -32602, "params must be an object")
        try:
            result = fn(Context(self, rid), **params)
        except TypeError as e:          # wrong/missing parameter names
            return self._error(rid, -32602, f"invalid params: {e}")
        except DocMasterError as e:
            log.warning("%s failed: %s %s", method, e.code, e)
            err = e.to_rpc(); return self._error(rid, err["code"], err["message"], err["data"])
        except Exception as e:          # noqa: BLE001
            log.exception("%s crashed", method)
            return self._error(rid, -32000, f"internal error: {type(e).__name__}: {e}", {"code": "INTERNAL_ERROR", "type": type(e).__name__, "detail": str(e)[:500]})
        if rid is not None:
            try:
                self.send({"jsonrpc": "2.0", "id": rid, "result": result})
            except (TypeError, ValueError) as e:          # result not serialisable: answer with an error, never silence
                log.exception("%s produced an unserialisable result", method)
                self._error(rid, -32000, f"internal error: result not serialisable: {e}", {"code": "INTERNAL_ERROR", "type": type(e).__name__})
