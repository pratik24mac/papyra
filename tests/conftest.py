import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


@pytest.fixture(autouse=True)
def _lift_socket_guard():
    """build_methods installs the process-wide offline socket guard; never let it leak between tests."""
    yield
    from docmaster import net
    net.uninstall_guard()
