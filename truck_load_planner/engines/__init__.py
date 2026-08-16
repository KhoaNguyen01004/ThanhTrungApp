import os
from typing import Optional

from truck_load_planner.engines.base import PackingEngine


ENGINE_INTERNAL = "internal"
ENGINE_PY3DBP = "py3dbp"

_DEFAULT_ENGINE = ENGINE_INTERNAL


def get_engine(name: Optional[str] = None) -> PackingEngine:
    resolved = name or os.environ.get("PACKING_ENGINE", _DEFAULT_ENGINE)

    if resolved == ENGINE_PY3DBP:
        from truck_load_planner.engines.py3dbp.adapter import Py3dbpPackingEngine
        return Py3dbpPackingEngine()
    elif resolved == ENGINE_INTERNAL:
        from truck_load_planner.engines.internal.engine import InternalPackingEngine
        return InternalPackingEngine()
    else:
        raise ValueError(
            f"Unknown packing engine '{resolved}'. "
            f"Choose: {ENGINE_INTERNAL}, {ENGINE_PY3DBP}"
        )


def list_engines() -> list[str]:
    return [ENGINE_INTERNAL, ENGINE_PY3DBP]
