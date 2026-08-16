from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Container:
    id: Optional[int] = None
    name: str = ""
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    payload_kg: float = 0.0
    features: list = field(default_factory=list)

    @property
    def volume_m3(self) -> float:
        return (self.length * self.width * self.height) / 1_000_000_000

    def to_dict(self) -> dict:
        d = asdict(self)
        d["volume_m3"] = self.volume_m3
        return d

    @staticmethod
    def from_dict(data: dict) -> "Container":
        return Container(
            id=data.get("id"),
            name=data.get("name", ""),
            length=data.get("length",
                           data.get("cargo_length_mm", 0)),
            width=data.get("width",
                          data.get("cargo_width_mm", 0)),
            height=data.get("height",
                           data.get("cargo_height_mm", 0)),
            payload_kg=data.get("payload_kg", 0),
            features=data.get("features", []),
        )
