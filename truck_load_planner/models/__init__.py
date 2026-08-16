import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ContainerConfig:
    id: Optional[int] = None
    name: str = ""
    cargo_length_mm: float = 0.0
    cargo_width_mm: float = 0.0
    cargo_height_mm: float = 0.0
    payload_kg: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Joined
    features: list = field(default_factory=list)

    @property
    def cargo_volume_m3(self) -> float:
        return (self.cargo_length_mm * self.cargo_width_mm * self.cargo_height_mm) / 1_000_000_000

    def to_dict(self):
        d = asdict(self)
        d["cargo_volume_m3"] = self.cargo_volume_m3
        if self.features:
            d["features"] = [f.to_dict() for f in self.features]
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            name=row.get("name", ""),
            cargo_length_mm=row["cargo_length_mm"],
            cargo_width_mm=row["cargo_width_mm"],
            cargo_height_mm=row["cargo_height_mm"],
            payload_kg=row.get("payload_kg", 0),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class ContainerFeature:
    id: Optional[int] = None
    container_config_id: int = 0
    feature_type: str = ""
    label: str = ""
    geometry_json: str = "{}"
    created_at: Optional[str] = None

    @property
    def geometry(self) -> dict:
        if isinstance(self.geometry_json, str):
            try:
                return json.loads(self.geometry_json)
            except (json.JSONDecodeError, TypeError):
                return {}
        return self.geometry_json or {}

    def to_dict(self):
        d = asdict(self)
        d["geometry"] = self.geometry
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        geo = row.get("geometry_json", "{}")
        if isinstance(geo, dict):
            geo = json.dumps(geo)
        return cls(
            id=row["id"],
            container_config_id=row["container_config_id"],
            feature_type=row["feature_type"],
            label=row.get("label", ""),
            geometry_json=geo,
            created_at=row.get("created_at"),
        )


@dataclass
class Package:
    id: Optional[int] = None
    name: str = ""
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    weight_kg: float = 0.0
    allow_stacking: bool = False
    allow_rotation: bool = False
    fragile: bool = False
    color: str = "#3b82f6"
    max_top_weight_kg: float = 0.0
    max_stack_layers: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def volume_m3(self) -> float:
        return (self.length * self.width * self.height) / 1_000_000_000

    def to_dict(self):
        d = asdict(self)
        d["volume_m3"] = self.volume_m3
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            name=row["name"],
            length=row["length"],
            width=row["width"],
            height=row["height"],
            weight_kg=row["weight_kg"],
            allow_stacking=bool(row.get("allow_stacking", 0)),
            allow_rotation=bool(row.get("allow_rotation", 0)),
            fragile=bool(row.get("fragile", 0)),
            color=row.get("color", "#3b82f6"),
            max_top_weight_kg=float(row.get("max_top_weight_kg", 0.0)),
            max_stack_layers=int(row.get("max_stack_layers", 0)),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class Shipment:
    id: Optional[int] = None
    customer_name: str = ""
    reference_number: str = ""
    notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            customer_name=row["customer_name"],
            reference_number=row.get("reference_number", ""),
            notes=row.get("notes", ""),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class ShipmentItem:
    id: Optional[int] = None
    shipment_id: int = 0
    package_id: int = 0
    quantity: int = 1
    notes: str = ""
    created_at: Optional[str] = None
    package: Optional[Package] = None

    def to_dict(self):
        d = asdict(self)
        if self.package:
            d["package"] = self.package.to_dict()
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            shipment_id=row["shipment_id"],
            package_id=row["package_id"],
            quantity=row.get("quantity", 1),
            notes=row.get("notes", ""),
            created_at=row.get("created_at"),
        )


@dataclass
class LoadPlan:
    id: Optional[int] = None
    name: str = ""
    vehicle_id: int = 0
    shipment_id: Optional[int] = None
    planner: str = ""
    notes: str = ""
    status: str = "draft"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Joined fields
    container: Optional[ContainerConfig] = None
    placements: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        if self.container:
            d["container"] = self.container.to_dict()
        if self.placements:
            d["placements"] = [p.to_dict() for p in self.placements]
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            name=row.get("name", ""),
            vehicle_id=row.get("vehicle_id", 0),
            shipment_id=row.get("shipment_id"),
            planner=row.get("planner", ""),
            notes=row.get("notes", ""),
            status=row.get("status", "draft"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class Placement:
    id: Optional[int] = None
    load_plan_id: int = 0
    shipment_item_id: Optional[int] = None
    package_id: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rotation: int = 0
    stack_level: int = 0
    load_sequence: Optional[int] = None
    created_at: Optional[str] = None
    package: Optional[Package] = None

    def to_dict(self):
        d = asdict(self)
        if self.package:
            d["package"] = self.package.to_dict()
        return d

    @classmethod
    def from_row(cls, row: dict):
        if not row:
            return None
        return cls(
            id=row["id"],
            load_plan_id=row["load_plan_id"],
            shipment_item_id=row.get("shipment_item_id"),
            package_id=row["package_id"],
            x=row["x"],
            y=row["y"],
            z=row["z"],
            rotation=row.get("rotation", 0),
            stack_level=row.get("stack_level", 0),
            load_sequence=row.get("load_sequence"),
            created_at=row.get("created_at"),
        )
