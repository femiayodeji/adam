from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from adam.skeleton import SKELETON_MAP

_KNOWN_BONES: frozenset[str] = frozenset(SKELETON_MAP.keys())


# ── LLM output models ────────────────────────────────────────────────────────

class BoneRotation(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class BoneKeyframe(BaseModel):
    name: str
    rotation: BoneRotation

    @field_validator("name")
    @classmethod
    def name_must_be_known(cls, v: str) -> str:
        if v not in _KNOWN_BONES:
            raise ValueError(f"Unknown bone: {v!r}")
        return v


class Keyframe(BaseModel):
    time: float
    bones: list[BoneKeyframe]
    easing: Literal["linear", "ease-in-out"] = "ease-in-out"
    grounded: bool = True


class MotionPlan(BaseModel):
    description: str
    keyframes: list[Keyframe]
    loop: bool = False
    totalDuration: float

    @model_validator(mode="after")
    def validate_structure(self) -> "MotionPlan":
        if len(self.keyframes) < 2:
            raise ValueError("Must have at least 2 keyframes")
        if self.keyframes[0].time != 0.0:
            raise ValueError("First keyframe must be at time=0")
        if self.totalDuration <= 0:
            raise ValueError("totalDuration must be > 0")
        return self

    def clamp_rotations(self) -> None:
        """Clamp bone rotations to declared skeleton ranges (in-place, warns only)."""
        for kf in self.keyframes:
            for b in kf.bones:
                bone_def = SKELETON_MAP.get(b.name)
                if not bone_def:
                    continue
                ranges = bone_def["range"]
                if "x" in ranges:
                    b.rotation.x = max(ranges["x"][0], min(ranges["x"][1], b.rotation.x))
                if "y" in ranges:
                    b.rotation.y = max(ranges["y"][0], min(ranges["y"][1], b.rotation.y))
                if "z" in ranges:
                    b.rotation.z = max(ranges["z"][0], min(ranges["z"][1], b.rotation.z))


class AnimationResponse(BaseModel):
    animations: list[MotionPlan] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalise_payload(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"animations": data}
        if isinstance(data, dict) and "animations" not in data and "keyframes" in data:
            return {"animations": [data]}
        return data

    def clamp_rotations(self) -> None:
        for animation in self.animations:
            animation.clamp_rotations()

    @property
    def primary(self) -> MotionPlan:
        return self.animations[0]

    @property
    def summary_text(self) -> str:
        return " -> ".join(animation.description for animation in self.animations)

    def payload(self) -> dict[str, Any]:
        data = self.model_dump()
        data["motion"] = data["animations"][0]
        return data


# ── History models ────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: Literal["user", "assistant"]
    # For user: raw command text.
    # For assistant: animation description summary only (NOT the full JSON — saves ~90% tokens).
    content: str
    motion_summary: str | None = None   # full animation JSON string, stored but not sent to LLM
    timestamp: float = field(default_factory=time.time)
