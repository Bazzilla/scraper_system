"""Map scraper names to their modules via dynamic import.

Resolves a configured module path to its ``run()`` callable.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable


def get_scraper(module: str) -> Callable[..., Any]:
    """Return the ``run()`` callable for the given module path.

    Raises:
        ValueError: If the module cannot be imported or has no ``run``.
    """
    try:
        module_obj = importlib.import_module(module)
    except ImportError as error:
        raise ValueError(f"Unknown scraper module: {module!r}") from error

    run = getattr(module_obj, "run", None)
    if not callable(run):
        raise ValueError(f"Module {module!r} has no callable run()")

    return run