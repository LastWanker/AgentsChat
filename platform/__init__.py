"""
避免与标准库 platform 同名导致的属性缺失：
- 加载标准库 platform 模块并通过 __getattr__ 透传其属性；
- 保持本目录下 world/router 等子模块的正常导入。
"""

from importlib.util import module_from_spec, spec_from_file_location
import os
import sysconfig

_stdlib_platform_path = os.path.join(sysconfig.get_paths()["stdlib"], "platform.py")
_stdlib_spec = spec_from_file_location("_stdlib_platform", _stdlib_platform_path)
_stdlib_platform = module_from_spec(_stdlib_spec)  # type: ignore[arg-type]
if _stdlib_spec and _stdlib_spec.loader:
    _stdlib_spec.loader.exec_module(_stdlib_platform)


def __getattr__(name):
    if hasattr(_stdlib_platform, name):
        return getattr(_stdlib_platform, name)
    raise AttributeError(name)