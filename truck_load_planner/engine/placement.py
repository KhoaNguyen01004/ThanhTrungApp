from dataclasses import dataclass, asdict
from typing import Optional
from .package import Package


_placement_uid_counter = [0]


def _next_placement_uid() -> int:
    _placement_uid_counter[0] += 1
    return _placement_uid_counter[0]


@dataclass
class Placement:
    package_id: int
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rotation: int = 0
    load_sequence: Optional[int] = None
    package: Optional[Package] = None
    door_used: str = "rear"

    def __post_init__(self):
        self._uid = _next_placement_uid()

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.package:
            d["_package"] = self.package
        return d

    @staticmethod
    def from_dict(data: dict) -> "Placement":
        pkg = data.get("_package")
        if pkg is None and data.get("package"):
            if isinstance(data["package"], dict):
                pkg = Package.from_dict(data["package"])
            else:
                pkg = data["package"]
        if pkg is None and data.get("package_id"):
            legacy = {}
            for k in ("id", "name", "length", "width", "height", "weight_kg",
                      "allow_stacking", "allow_rotation", "fragile", "color",
                      "_name", "_weight_kg", "_length", "_width", "_height"):
                if k in data:
                    legacy[k] = data[k]
            if legacy.get("_name") or legacy.get("name"):
                pkg = Package.from_dict(legacy)
        return Placement(
            package_id=data["package_id"],
            x=data.get("x", 0),
            y=data.get("y", 0),
            z=data.get("z", 0),
            rotation=data.get("rotation", 0),
            load_sequence=data.get("load_sequence"),
            package=pkg,
        )
