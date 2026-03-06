from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


Incoterm = Literal["FOB", "CIF", "CFR", "EXW", "DDP", "DAP", "FCA", "CPT", "CIP", "DPU"]


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    subject: str = ""
    body: str = ""


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str

    product_line: Optional[Literal["pl_sea_import_lcl", "pl_sea_export_lcl"]] = None

    origin_port_code: Optional[str] = Field(default=None, description="5-letter UN/LOCODE")
    origin_port_name: Optional[str] = None

    destination_port_code: Optional[str] = Field(default=None, description="5-letter UN/LOCODE")
    destination_port_name: Optional[str] = None

    incoterm: Incoterm = "FOB"

    cargo_weight_kg: Optional[float] = None
    cargo_cbm: Optional[float] = None

    is_dangerous: bool = False

    @field_validator("origin_port_code", "destination_port_code")
    @classmethod
    def validate_port_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip().upper()
        if len(v2) != 5 or not v2.isalpha():
            return None
        return v2

    @field_validator("cargo_weight_kg", "cargo_cbm")
    @classmethod
    def validate_numeric(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0:
            return None
        # Keep explicit 0.0 if provided; round everything to 2 decimals for evaluation.
        return round(float(v), 2)

    @field_validator("incoterm", mode="before")
    @classmethod
    def normalize_incoterm(cls, v: object) -> str:
        if v is None:
            return "FOB"
        s = str(v).strip().upper()
        allowed = {"FOB", "CIF", "CFR", "EXW", "DDP", "DAP", "FCA", "CPT", "CIP", "DPU"}
        return s if s in allowed else "FOB"

