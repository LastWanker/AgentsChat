"""Namespace shim so `python -m agents_chat...` works from repo root."""

from pathlib import Path
import pkgutil
import sys

__path__ = pkgutil.extend_path(__path__, __name__)  # type: ignore[name-defined]
_src_pkg = Path(__file__).resolve().parent.parent / "src" / "agents_chat"
_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
if _src_pkg.exists():
    __path__.append(str(_src_pkg))  # type: ignore[attr-defined]
