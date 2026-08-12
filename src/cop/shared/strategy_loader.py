"""Dynamic brain-class loader for `[strategy] police_class`/`thief_class`
(PRD 13) — Table 22's own documented `"package.module:Class"` format,
finally consumed. `PrivateConfig.police_class` has been parsed since PRD 4
but never read by anything until this layer (its own docstring said so).

A bad or malicious dotted path raises loudly here rather than silently
falling back to `CopBrain` — a silent substitution would be an invisible,
ungraded change to which brain actually played a real match.
"""

from __future__ import annotations

import importlib

from ..reasoning.brain_base import BrainBase


def load_brain_class(dotted_path: str) -> type[BrainBase]:
    """Loads and validates `dotted_path`; raises `ValueError` on anything
    that isn't a real, importable `BrainBase` subclass — never returns a
    default on failure, since a caller that wanted a default wouldn't have
    called this at all."""
    module_path, separator, class_name = dotted_path.partition(":")
    if not separator or not module_path or not class_name:
        raise ValueError(
            f"police_class/thief_class must be 'package.module:ClassName', got {dotted_path!r}"
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ValueError(f"cannot import module {module_path!r} from {dotted_path!r}") from exc

    try:
        brain_cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(f"module {module_path!r} has no attribute {class_name!r}") from exc

    if not (isinstance(brain_cls, type) and issubclass(brain_cls, BrainBase)):
        raise ValueError(f"{dotted_path!r} is not a BrainBase subclass, got {brain_cls!r}")

    return brain_cls
