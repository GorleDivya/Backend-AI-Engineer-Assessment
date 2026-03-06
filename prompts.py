from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PromptVersion:
    name: str
    prompt: str


def _ports_block(port_rows: Iterable[dict]) -> str:
    # Provide a compact, deterministic list to the model.
    rows = [{"code": r["code"], "name": r["name"]} for r in port_rows]
    return json.dumps(rows, ensure_ascii=False, indent=2)


def get_prompt_versions(port_rows: list[dict]) -> list[PromptVersion]:
    ports_json = _ports_block(port_rows)

    v1 = PromptVersion(
        name="v1_basic",
        prompt=(
            "Extract shipment info from an LCL ocean freight pricing enquiry email.\n"
            "Return ONLY valid JSON with these keys:\n"
            "origin_port_code, destination_port_code, incoterm, cargo_weight_kg, cargo_cbm, is_dangerous.\n"
            "If unknown, use null. Incoterm default is FOB.\n"
            "\n"
            "Valid incoterms: FOB, CIF, CFR, EXW, DDP, DAP, FCA, CPT, CIP, DPU.\n"
        ),
    )

    v2 = PromptVersion(
        name="v2_with_ports",
        prompt=(
            "You are extracting structured data from freight forwarding pricing enquiry emails.\n"
            "\n"
            "Return ONLY JSON. Do not include any extra text.\n"
            "Use ONLY port codes from this reference list (UN/LOCODE). If a port is not in the list, use null.\n"
            "Port reference (code -> canonical name):\n"
            f"{ports_json}\n"
            "\n"
            "Fields to output (all required keys):\n"
            "- origin_port_code: string or null\n"
            "- destination_port_code: string or null\n"
            "- incoterm: one of FOB/CIF/CFR/EXW/DDP/DAP/FCA/CPT/CIP/DPU; if missing/ambiguous default to FOB\n"
            "- cargo_weight_kg: number (kg) or null; convert lbs->kg (lbs*0.453592) and tonnes/MT->kg (x*1000)\n"
            "- cargo_cbm: number (cbm) or null; do NOT calculate CBM from dimensions\n"
            "- is_dangerous: true if DG/hazardous/IMO/IMDG/Class N; false if explicitly non-DG/non-hazardous or not mentioned\n"
        ),
    )

    v3 = PromptVersion(
        name="v3_business_rules",
        prompt=(
            "Task: Extract the FIRST shipment in the email body (if multiple shipments are mentioned).\n"
            "Body takes precedence over subject if there is any conflict.\n"
            "\n"
            "Return ONLY JSON with EXACTLY these keys:\n"
            "origin_port_code, destination_port_code, incoterm, cargo_weight_kg, cargo_cbm, is_dangerous.\n"
            "\n"
            "Rules:\n"
            "- Use ONLY port codes from the reference list below; otherwise null.\n"
            "- If origin/destination are ambiguous (more than one possible port for a field), choose the best match for the described origin->destination lane.\n"
            "- Incoterm: normalize to uppercase. If missing, unrecognizable, or ambiguous (e.g. 'FOB or CIF'), output FOB.\n"
            "- cargo_weight_kg and cargo_cbm: output null if TBD/N/A/to be confirmed; round to 2 decimals.\n"
            "- If weight is in lbs, convert to kg (lbs*0.453592). If in tonnes/MT, multiply by 1000.\n"
            "- Do NOT infer numbers not present.\n"
            "- Dangerous goods: true if DG/dangerous/hazardous/IMO/IMDG/'Class <number>'; false if explicitly non-DG/non-hazardous/not dangerous; default false.\n"
            "\n"
            "Port reference (code -> canonical name):\n"
            f"{ports_json}\n"
        ),
    )

    return [v1, v2, v3]

