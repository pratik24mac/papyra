"""Application settings persisted as JSON in the app data directory (Rust passes `--data-dir`).

Only non-sensitive preferences live here (output folder, email preferences later). OAuth tokens
never do: they belong in the OS credential store (spec §13).
"""
from __future__ import annotations
import json, os, threading
from pathlib import Path
from ..errors import DocMasterError, OutputPathError
from .paths import ensure_dir


class SettingInvalid(DocMasterError):
    code, rpc_code, user_message = "SETTING_INVALID", -32060, "That setting value is not allowed."


KNOWN = {"output_dir": str, "imap_account": dict, "offline_mode": bool, "keep_history": bool}


class Settings:
    def __init__(self, data_dir: Path, default_output_dir: Path):
        self.path = data_dir / "settings.json"
        self.defaults = {"output_dir": str(default_output_dir), "imap_account": None, "offline_mode": True, "keep_history": True}
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            self._data = {k: v for k, v in json.loads(self.path.read_text(encoding="utf8")).items() if k in KNOWN}
        except (OSError, ValueError):
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=1), encoding="utf8")
        tmp.replace(self.path)

    def all(self) -> dict:
        with self._lock:
            merged = {**self.defaults, **self._data}
        return {**merged, "defaults": dict(self.defaults), "settings_file": str(self.path)}

    def output_dir(self) -> Path:
        with self._lock:
            return Path(self._data.get("output_dir") or self.defaults["output_dir"])

    def set(self, key: str, value) -> dict:
        if key not in KNOWN:
            raise SettingInvalid(f"unknown setting '{key}'", data={"key": key})
        if value is None:                              # reset to default
            with self._lock:
                self._data.pop(key, None); self._save()
            return self.all()
        if key == "imap_account":
            from ..email.imap_draft import ImapAccount
            value = ImapAccount.from_dict(value).public() | {"drafts_folder": value.get("drafts_folder") or None}
        if not isinstance(value, KNOWN[key]):
            raise SettingInvalid(f"'{key}' must be a {KNOWN[key].__name__}", data={"key": key})
        if key == "output_dir":
            p = Path(os.path.expanduser(value))
            if not p.is_absolute():
                raise SettingInvalid("the output folder must be an absolute path", data={"key": key})
            ensure_dir(p)                              # raises OutputPathError when not writable
            value = str(p.resolve())
        with self._lock:
            self._data[key] = value; self._save()
        return self.all()
