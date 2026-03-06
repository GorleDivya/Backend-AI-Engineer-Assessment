from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from rapidfuzz import fuzz, process

from schemas import EmailInput, Extraction
from prompts import get_prompt_versions


ROOT = Path(__file__).resolve().parent

INCOTERMS = {"FOB", "CIF", "CFR", "EXW", "DDP", "DAP", "FCA", "CPT", "CIP", "DPU"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(s: str) -> str:
    s = s.lower()
    s = s.replace("\u2192", " to ")
    s = re.sub(r"[\t\r\n]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_is_dangerous(text: str) -> bool:
    t = normalize_text(text)
    neg = [
        r"\bnon[- ]dg\b",
        r"\bnon[- ]hazardous\b",
        r"\bnot dangerous\b",
        r"\bnon hazardous\b",
        r"\bnon[- ]dangerous\b",
    ]
    if any(re.search(p, t) for p in neg):
        return False

    pos = [
        r"\bdg\b",
        r"\bdangerous\b",
        r"\bhazardous\b",
        r"\bimo\b",
        r"\bimdg\b",
        r"\bclass\s*\d+\b",
    ]
    return any(re.search(p, t) for p in pos)


def parse_incoterm(text: str) -> str:
    t = normalize_text(text)
    # If the email suggests multiple incoterms ("FOB or CIF"), default to FOB.
    if re.search(r"\b(fob|cif|cfr|exw|ddp|dap|fca|cpt|cip|dpu)\b\s+or\s+\b", t):
        return "FOB"
    for inc in INCOTERMS:
        if re.search(rf"\b{inc.lower()}\b", t):
            return inc
    return "FOB"


def _has_tbd_token(text: str) -> bool:
    t = normalize_text(text)
    return bool(re.search(r"\b(tbd|n/a|na|to be confirmed|to be advise|tbc)\b", t))


def parse_numbers(text: str) -> tuple[Optional[float], Optional[float]]:
    """
    Extract weight (kg) and cbm independently. Does not compute cbm from dimensions.
    """
    if _has_tbd_token(text):
        # Still allow explicit 0 values even if "TBD" appears elsewhere.
        pass

    t = normalize_text(text)

    # CBM
    cbm: Optional[float] = None
    cbm_match = re.search(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:cbm|cmb)\b", t)
    if cbm_match:
        num = cbm_match.group("num").replace(",", "")
        try:
            cbm = round(float(num), 2)
        except ValueError:
            cbm = None

    # Weight
    weight_kg: Optional[float] = None
    # kg/kgs
    kg_match = re.search(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:kg|kgs)\b", t)
    if kg_match:
        num = kg_match.group("num").replace(",", "")
        try:
            weight_kg = round(float(num), 2)
        except ValueError:
            weight_kg = None
    else:
        lbs_match = re.search(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:lb|lbs)\b", t)
        if lbs_match:
            num = lbs_match.group("num").replace(",", "")
            try:
                weight_kg = round(float(num) * 0.453592, 2)
            except ValueError:
                weight_kg = None
        else:
            mt_match = re.search(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:mt|tonne|tonnes)\b", t)
            if mt_match:
                num = mt_match.group("num").replace(",", "")
                try:
                    weight_kg = round(float(num) * 1000.0, 2)
                except ValueError:
                    weight_kg = None

    if _has_tbd_token(text):
        # Treat numeric fields as null if they are described as TBD/N/A.
        # Keep explicit "0 kg" or "0 cbm".
        if not re.search(r"\b0(?:[.,]0+)?\s*(?:kg|kgs|lb|lbs|mt|tonne|tonnes)\b", t):
            weight_kg = None
        if not re.search(r"\b0(?:[.,]0+)?\s*(?:cbm|cmb)\b", t):
            cbm = None

    if weight_kg is not None and weight_kg < 0:
        weight_kg = None
    if cbm is not None and cbm < 0:
        cbm = None

    return weight_kg, cbm


@dataclass(frozen=True)
class PortEntry:
    code: str
    name: str


class PortMatcher:
    def __init__(self, port_rows: list[dict]):
        self.entries: list[PortEntry] = [PortEntry(code=r["code"].upper(), name=r["name"]) for r in port_rows]

        # Build alias -> (code, canonical_name)
        self.alias_to_entry: dict[str, PortEntry] = {}
        for e in self.entries:
            for alias in self._aliases_for_name(e.name):
                # Keep the best alias mapping; duplicates are OK (same code).
                self.alias_to_entry.setdefault(alias, e)

        self.aliases = list(self.alias_to_entry.keys())

        self.codes_to_default_name: dict[str, str] = {}
        for e in self.entries:
            # Default to the shortest "clean" name for the code.
            self.codes_to_default_name.setdefault(e.code, e.name)
            cur = self.codes_to_default_name[e.code]
            if self._name_sort_key(e.name) < self._name_sort_key(cur):
                self.codes_to_default_name[e.code] = e.name

    @staticmethod
    def _name_sort_key(name: str) -> tuple[int, int]:
        # Prefer short and not overly generic.
        n = name.lower()
        penalty = 0
        if " / " in n:
            penalty += 3
        if "india" in n or "japan" in n:
            penalty += 5
        return (penalty, len(n))

    @staticmethod
    def _aliases_for_name(name: str) -> set[str]:
        n = normalize_text(name)
        # Split combined variants like "Shenzhen / Guangzhou"
        parts = [p.strip() for p in re.split(r"/", n) if p.strip()]

        aliases: set[str] = set()
        for p in parts:
            p2 = re.sub(r"[()]", " ", p)
            p2 = re.sub(r"\bport\b", " ", p2)
            p2 = re.sub(r"\bindia\b", " ", p2)
            p2 = re.sub(r"\bjapan\b", " ", p2)
            p2 = re.sub(r"\s+", " ", p2).strip()
            if p2:
                aliases.add(p2)

            # Add ICD-stripped alias too (so "Chennai ICD" matches "Chennai")
            p3 = re.sub(r"\bicd\b", " ", p2)
            p3 = re.sub(r"\s+", " ", p3).strip()
            if p3 and p3 != p2:
                aliases.add(p3)
        return aliases

    def code_in_reference(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        c = code.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}", c):
            return None
        if any(e.code == c for e in self.entries):
            return c
        return None

    def name_for_code(self, code: Optional[str], *, prefer_icd: bool = False) -> Optional[str]:
        if code is None:
            return None
        c = code.strip().upper()
        if prefer_icd:
            icd_names = [e.name for e in self.entries if e.code == c and "icd" in e.name.lower()]
            if icd_names:
                # Prefer the shortest ICD variant
                return sorted(icd_names, key=lambda x: len(x))[0]
        return self.codes_to_default_name.get(c)

    def match(self, text: str, *, prefer_icd: bool = False) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (code, matched_reference_name) using fuzzy matching over known aliases.
        """
        t = normalize_text(text)
        if not t:
            return None, None

        best = process.extractOne(t, self.aliases, scorer=fuzz.WRatio)
        if not best:
            return None, None
        alias, score, _idx = best
        if score < 78:
            return None, None
        entry = self.alias_to_entry[alias]

        code = entry.code
        name = self.name_for_code(code, prefer_icd=prefer_icd) if prefer_icd else entry.name
        return code, name

    def match_from_email_text(self, subject: str, body: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Heuristic lane extraction used as a fallback when no LLM key is present.
        """
        body_t = normalize_text(body)
        subj_t = normalize_text(subject)

        # Prefer explicit UN/LOCODE codes in body
        def find_codes(t: str) -> list[str]:
            return [m.group(0).upper() for m in re.finditer(r"\b[A-Z]{5}\b", t.upper())]

        codes = [c for c in find_codes(body) if self.code_in_reference(c)]
        if len(codes) >= 2:
            o, d = codes[0], codes[1]
            prefer_icd = "icd" in body_t
            return o, self.name_for_code(o, prefer_icd=prefer_icd), d, self.name_for_code(d, prefer_icd=prefer_icd)

        # Try "from X to Y" pattern on body first, else subject
        lane_text = body_t or subj_t
        lane_text = lane_text.replace(" ex ", " from ")

        m = re.search(r"\bfrom\s+(?P<o>[^,.;\n]+?)\s+\bto\b\s+(?P<d>[^,.;\n]+)", lane_text)
        if not m:
            m = re.search(r"(?P<o>[^,.;\n]+?)\s+\bto\b\s+(?P<d>[^,.;\n]+)", lane_text)
        if m:
            o_raw = m.group("o")
            d_raw = m.group("d")
            prefer_icd = ("icd" in o_raw.lower()) or ("icd" in d_raw.lower()) or ("icd" in body_t)
            o_code, o_name = self.match(o_raw, prefer_icd=prefer_icd)
            d_code, d_name = self.match(d_raw, prefer_icd=prefer_icd)
            return o_code, o_name, d_code, d_name

        # Fallback: best two port matches from body
        prefer_icd = "icd" in body_t
        o_code, o_name = self.match(body_t, prefer_icd=prefer_icd)
        d_code, d_name = self.match(subj_t, prefer_icd=prefer_icd)
        return o_code, o_name, d_code, d_name


def compute_product_line(origin_code: Optional[str], destination_code: Optional[str]) -> Optional[str]:
    if destination_code and destination_code.upper().startswith("IN"):
        return "pl_sea_import_lcl"
    if origin_code and origin_code.upper().startswith("IN"):
        return "pl_sea_export_lcl"
    return None


def llm_extract_fields(
    *,
    api_key: str,
    model: str,
    prompt: str,
    email_subject: str,
    email_body: str,
    max_retries: int = 3,
) -> dict[str, Any]:
    from groq import Groq  # lazy import so script runs without it installed

    client = Groq(api_key=api_key)
    content = f"SUBJECT:\n{email_subject}\n\nBODY:\n{email_body}"

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt + "\n\n" + content}],
                temperature=0,
            )
            txt = (resp.choices[0].message.content or "").strip()
            # Best-effort JSON extraction in case the model wraps it.
            start = txt.find("{")
            end = txt.rfind("}")
            if start != -1 and end != -1 and end > start:
                txt = txt[start : end + 1]
            data = json.loads(txt)
            if not isinstance(data, dict):
                raise ValueError("LLM did not return a JSON object")
            return data
        except Exception as e:  # noqa: BLE001 - we want robust retries for API issues
            last_err = e
            if attempt >= max_retries:
                break
            # Exponential backoff with jitter.
            sleep_s = (2**attempt) + random.uniform(0, 0.5)
            time.sleep(sleep_s)
    raise RuntimeError(f"LLM extraction failed after retries: {last_err}")


def coerce_port(
    matcher: PortMatcher,
    value: Any,
    *,
    prefer_icd: bool,
    full_text: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Accepts either a code or a name-ish string and returns (code, name).
    """
    if value is None:
        return None, None
    s = str(value).strip()
    if not s:
        return None, None

    code = matcher.code_in_reference(s)
    if code:
        name = matcher.name_for_code(code, prefer_icd=("icd" in normalize_text(full_text)) or prefer_icd)
        return code, name

    code2, name2 = matcher.match(s, prefer_icd=prefer_icd)
    return code2, name2


def build_extraction(
    email: EmailInput,
    matcher: PortMatcher,
    llm_data: Optional[dict[str, Any]],
) -> Extraction:
    text_for_rules = f"{email.subject}\n{email.body}"
    prefer_icd = "icd" in normalize_text(text_for_rules)

    if llm_data is None:
        o_code, o_name, d_code, d_name = matcher.match_from_email_text(email.subject, email.body)
        inc = parse_incoterm(text_for_rules)
        weight_kg, cbm = parse_numbers(text_for_rules)
        is_dg = detect_is_dangerous(text_for_rules)
    else:
        o_code, o_name = coerce_port(
            matcher,
            llm_data.get("origin_port_code") or llm_data.get("origin_port") or llm_data.get("origin"),
            prefer_icd=prefer_icd,
            full_text=text_for_rules,
        )
        d_code, d_name = coerce_port(
            matcher,
            llm_data.get("destination_port_code") or llm_data.get("destination_port") or llm_data.get("destination"),
            prefer_icd=prefer_icd,
            full_text=text_for_rules,
        )

        inc = parse_incoterm(str(llm_data.get("incoterm") or "") + "\n" + text_for_rules)

        weight_kg = llm_data.get("cargo_weight_kg")
        cbm = llm_data.get("cargo_cbm")
        # If model didn't provide numbers (or provided strings), fall back to regex parser.
        if not isinstance(weight_kg, (int, float)) and weight_kg is not None:
            weight_kg = None
        if not isinstance(cbm, (int, float)) and cbm is not None:
            cbm = None
        if weight_kg is None or cbm is None:
            w2, c2 = parse_numbers(text_for_rules)
            weight_kg = weight_kg if weight_kg is not None else w2
            cbm = cbm if cbm is not None else c2

        # Dangerous goods: deterministic rule-based (more reliable than LLM).
        is_dg = detect_is_dangerous(text_for_rules)

    product_line = compute_product_line(o_code, d_code)
    # If both are non-India (rare), product_line stays null.

    return Extraction(
        id=email.id,
        product_line=product_line,
        origin_port_code=o_code,
        origin_port_name=o_name if o_code else None,
        destination_port_code=d_code,
        destination_port_name=d_name if d_code else None,
        incoterm=inc,
        cargo_weight_kg=weight_kg,
        cargo_cbm=cbm,
        is_dangerous=bool(is_dg),
    )


def main() -> None:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile").strip() or "llama-3.1-70b-versatile"

    emails_path = ROOT / "emails_input.json"
    ports_path = ROOT / "port_codes_reference.json"
    out_path = ROOT / "output.json"

    port_rows = load_json(ports_path)
    matcher = PortMatcher(port_rows)
    prompt_versions = get_prompt_versions(port_rows)
    prompt = next(p.prompt for p in prompt_versions if p.name == "v3_business_rules")

    emails_raw = load_json(emails_path)
    emails = [EmailInput.model_validate(e) for e in emails_raw]

    outputs: list[dict[str, Any]] = []
    for email in emails:
        llm_data: Optional[dict[str, Any]] = None
        if api_key:
            try:
                llm_data = llm_extract_fields(
                    api_key=api_key,
                    model=model,
                    prompt=prompt,
                    email_subject=email.subject,
                    email_body=email.body,
                )
            except Exception:
                # Per spec: do not skip; output nulls if extraction fails.
                llm_data = None
                ex = Extraction(
                    id=email.id,
                    product_line=None,
                    origin_port_code=None,
                    origin_port_name=None,
                    destination_port_code=None,
                    destination_port_name=None,
                    incoterm="FOB",
                    cargo_weight_kg=None,
                    cargo_cbm=None,
                    is_dangerous=False,
                )
                outputs.append(ex.model_dump())
                continue

        ex = build_extraction(email, matcher, llm_data)
        outputs.append(ex.model_dump())

    dump_json(out_path, outputs)
    print(f"Wrote {len(outputs)} rows to {out_path}")
    if not api_key:
        print("Note: GROQ_API_KEY not set; used heuristic fallback (lower accuracy).")


if __name__ == "__main__":
    main()

