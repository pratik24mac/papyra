"""OS credential store (macOS Keychain, Windows Credential Manager) through `keyring`, with
chunking because Windows caps a credential blob at 2560 bytes. Nothing here is logged."""
from __future__ import annotations
import math
from ..errors import DocMasterError

SERVICE = "papyra"
CHUNK = 1000


class CredentialStoreUnavailable(DocMasterError):
    code, rpc_code, user_message = "CREDENTIAL_STORE_UNAVAILABLE", -32077, "The system credential store is not available."


class CredentialStore:
    def __init__(self, backend=None, service: str = SERVICE):
        if backend is None:
            import keyring
            backend = keyring
        self._kr, self.service = backend, service

    def set(self, key: str, secret: str) -> None:
        try:
            parts = [secret[i:i + CHUNK] for i in range(0, len(secret), CHUNK)] or [""]
            self._kr.set_password(self.service, f"{key}:count", str(len(parts)))
            for i, part in enumerate(parts):
                self._kr.set_password(self.service, f"{key}:{i}", part)
        except Exception as e:  # noqa: BLE001
            raise CredentialStoreUnavailable(data={"reason": type(e).__name__})

    def get(self, key: str) -> str | None:
        try:
            count = self._kr.get_password(self.service, f"{key}:count")
            if count is None:
                return None
            parts = [self._kr.get_password(self.service, f"{key}:{i}") for i in range(int(count))]
            return None if any(p is None for p in parts) else "".join(parts)
        except Exception as e:  # noqa: BLE001
            raise CredentialStoreUnavailable(data={"reason": type(e).__name__})

    def delete(self, key: str) -> None:
        try:
            count = self._kr.get_password(self.service, f"{key}:count")
            for name in ([f"{key}:count"] + [f"{key}:{i}" for i in range(int(count))]) if count else []:
                try: self._kr.delete_password(self.service, name)
                except Exception: pass  # noqa: BLE001
        except Exception as e:  # noqa: BLE001
            raise CredentialStoreUnavailable(data={"reason": type(e).__name__})
