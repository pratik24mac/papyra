"""The RPC method list must agree across Python (implementation), Rust (allow-list) and TypeScript (client)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rpc_method_names_agree():
    py = set(re.findall(r'"(\w+\.\w+)":\s*\w+', (ROOT / "backend/docmaster/rpc/methods.py").read_text()))
    rust = set(re.findall(r'"(\w+\.\w+)"', re.search(r"ALLOWED_METHODS[^;]+;", (ROOT / "apps/desktop/src-tauri/src/backend.rs").read_text()).group(0)))
    ts = set(re.findall(r'call<[^>]+>\("(\w+\.\w+)"', (ROOT / "apps/desktop/src/api/backend.ts").read_text()))
    assert "system.shutdown" in py and "system.shutdown" not in rust          # never callable from the UI
    assert rust == py - {"system.shutdown"}, f"rust allow-list {rust} != python methods {py}"
    assert ts <= rust, f"TypeScript calls methods the UI may not use: {ts - rust}"


def test_error_codes_agree():
    py = set(re.findall(r'code, rpc_code, user_message = "(\w+)"', (ROOT / "backend/docmaster/errors.py").read_text()))
    ts = set(re.findall(r'"([A-Z_]+)"', re.search(r"export type ErrorCode =[^;]+;", (ROOT / "apps/desktop/src/api/types.ts").read_text()).group(0)))
    assert py <= ts, f"error codes missing in TypeScript: {py - ts}"
