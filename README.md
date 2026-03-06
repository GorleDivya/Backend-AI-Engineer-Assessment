# Backend / AI Engineer Assessment

**Company:** Task Harmony
**Time Limit:** 3-4 hours
**Submission:** GitHub repository link
**Follow-up:** 15-20 min technical discussion on your submission

---

## Overview

Build an LLM-powered email extraction system for freight forwarding pricing enquiries.

**What you'll do:**
1. Process 50 sample emails using an LLM
2. Extract structured shipment details
3. Measure accuracy against provided ground truth
4. Document your iteration process

**What we'll evaluate:**
- Your extraction accuracy on provided emails
- Your code quality and approach
- **Your solution on 171 hidden test emails** (not provided)

---

## Context

Freight forwarding companies receive pricing enquiry emails like:

```
Subject: RATE REQ // SEA // LCL // HONG KONG TO CHENNAI
Body: Dear Sir, Please quote LCL rate from Hong Kong to Chennai, 5 CBM, FOB terms.
```

Your system should extract:
```json
{
  "product_line": "pl_sea_import_lcl",
  "origin_port_code": "HKHKG",
  "destination_port_code": "INMAA",
  "incoterm": "FOB",
  "cargo_cbm": 5.0
}
```

---

## Business Rules

### Core Rules

| Rule | Logic |
|------|-------|
| **Product Line** | Destination is India → `pl_sea_import_lcl`; Origin is India → `pl_sea_export_lcl` (all emails in this assessment are LCL shipments) |
| **India Detection** | Indian ports have UN/LOCODE starting with `IN` (e.g., INMAA, INNSA, INBLR) |
| **Incoterm Default** | If not mentioned → `FOB` |
| **Null Handling** | Missing values → `null` (not `0` or `""`) |
| **Port Codes** | UN/LOCODE format (5 letters: 2-letter country + 3-letter location) |
| **Port Names** | Always use the canonical name from `port_codes_reference.json` for the matched code, regardless of how the port was named in the email. If code is `null`, name is also `null` |

### Valid Incoterms

Recognize these incoterms (normalize to uppercase): `FOB`, `CIF`, `CFR`, `EXW`, `DDP`, `DAP`, `FCA`, `CPT`, `CIP`, `DPU`

If incoterm is unrecognizable or ambiguous (e.g., email says "FOB or CIF terms"), default to `FOB`.

### Dangerous Goods Detection

| Condition | Result |
|-----------|--------|
| Contains: "DG", "dangerous", "hazardous", "Class" + number (e.g., Class 3, Class 9), "IMO", "IMDG" | `is_dangerous: true` |
| Contains negations: "non-hazardous", "non-DG", "not dangerous", "non hazardous" (with or without hyphen) | `is_dangerous: false` |
| No mention | `is_dangerous: false` |

### Conflict Resolution

| Scenario | Rule |
|----------|------|
| **Subject vs Body conflict** | Body takes precedence (more detailed context) |
| **Multiple shipments in one email** | Extract the shipment that appears first in the email body |
| **Multiple ports mentioned** | Use origin→destination pair, not intermediate/transshipment ports |

**Example - Subject vs Body conflict:**
```
Subject: RATE REQ // FOB // HK TO MUMBAI
Body: Please quote CIF terms for shipment from Hong Kong to Chennai
Expected: incoterm="CIF", destination_port_code="INMAA" (body wins)
```

**Example - Multiple shipments:**
```
Body: "Please quote for two shipments: 1) Hong Kong to Chennai, 500kg and 2) Shanghai to Mumbai, 300kg"
Expected: origin_port_code="HKHKG", destination_port_code="INMAA", cargo_weight_kg=500.0 (first shipment only)
```

### Numeric Fields

| Rule | Details |
|------|---------|
| **Rounding** | Round `cargo_weight_kg` and `cargo_cbm` to 2 decimal places |
| **Validation** | Weight and CBM must be positive numbers or `null` |
| **TBD/N/A values** | "TBD", "N/A", "to be confirmed" → extract as `null` |
| **Zero values** | Explicit zero (e.g., "0 kg") → extract as `0`, not `null` |

### Unit Handling

| Unit | Conversion |
|------|------------|
| Weight in lbs | Convert to kg: `lbs × 0.453592`, round to 2 decimals |
| Weight in tonnes/MT | Convert to kg: `tonnes × 1000` |
| Dimensions (L×W×H) | Extract as `null` for CBM (do not calculate) |
| Weight AND CBM both mentioned | Extract both values independently |

**Example - Both weight and CBM:**
```
Email: "...shipment of 500 kg, 2.5 CBM..."
Expected: cargo_weight_kg=500.0, cargo_cbm=2.5
```

---

## Port Codes Reference

The `port_codes_reference.json` file has this structure:

```json
[
  {"code": "HKHKG", "name": "Hong Kong"},
  {"code": "INMAA", "name": "Chennai"},
  {"code": "CNSHA", "name": "Shanghai"}
]
```

- **code**: 5-letter UN/LOCODE (2-letter country + 3-letter location)
- **name**: Port name (may include variations like "Chennai ICD", "ICD Bangalore")

**Notes:**
- Some ports have multiple name entries mapping to the same code
- Common abbreviations (e.g., "HK" for Hong Kong) should be handled
- Exact matching strategy is up to you - document your approach in your README

---

## Output Schema

```json
{
  "id": "EMAIL_001",
  "product_line": "pl_sea_import_lcl",
  "origin_port_code": "HKHKG",
  "origin_port_name": "Hong Kong",
  "destination_port_code": "INMAA",
  "destination_port_name": "Chennai",
  "incoterm": "FOB",
  "cargo_weight_kg": null,
  "cargo_cbm": 5.0,
  "is_dangerous": false
}
```

**Required:** Use Pydantic models for output validation. Numeric fields (`cargo_weight_kg`, `cargo_cbm`) should be `Optional[float]` type.

---

## LLM API

Use **Groq** (free, no credit card):
- Sign up: https://console.groq.com
- Model: `llama-3.1-70b-versatile` (or `llama-3.3-70b-versatile` if unavailable)
- **Important:** Set `temperature=0` for reproducible results

```python
from groq import Groq

client = Groq(api_key="your-key")
response = client.chat.completions.create(
    model="llama-3.1-70b-versatile",
    messages=[{"role": "user", "content": prompt}],
    temperature=0  # Required for reproducibility
)
```

**Rate Limits:** Groq free tier has rate limits (~30 requests/minute). Implement retry logic with exponential backoff. Processing 50 emails may take 5-10 minutes.

---

## Files Provided

| File | Description |
|------|-------------|
| `emails_input.json` | 50 sample emails (array of `{id, subject, body}`) |
| `ground_truth.json` | Expected outputs for accuracy measurement |
| `port_codes_reference.json` | UN/LOCODE mappings (47 ports) |

**Important:** The hidden test set uses the same `port_codes_reference.json` and follows similar patterns to the sample data. No new incoterms, product lines, or port codes beyond the reference file will appear.

---

## Deliverables

```
your-repo/
├── README.md           # Approach, metrics, prompt evolution, design answers
├── requirements.txt    # Dependencies
├── schemas.py          # Pydantic models
├── prompts.py          # Your prompts (show evolution v1→v2→v3)
├── extract.py          # Main script
├── evaluate.py         # Accuracy calculator
├── output.json         # Your results for all 50 emails
└── .env.example        # API key template
```

**Important:** Include your pre-generated `output.json`. We review code but may not re-run extraction.

---

## README Requirements

### 1. Setup Instructions
```bash
pip install -r requirements.txt
python extract.py      # Generates output.json
python evaluate.py     # Shows accuracy metrics
```

### 2. Prompt Evolution Log (Required)

Show your actual iteration process with **specific examples**:

```markdown
## Prompt Evolution

### v1: Basic extraction
- Accuracy: 62%
- Issues: Port codes wrong, missing incoterms
- Example: EMAIL_007 extracted "Chennai" instead of "INMAA"

### v2: Added UN/LOCODE examples
- Accuracy: 78%
- Issues: India detection failing for some ports
- Example: EMAIL_023 incorrectly set product_line for Nhava Sheva

### v3: Added business rules explicitly
- Accuracy: 88%
- Remaining issues: [describe with specific email IDs]
```

**Note:** Include specific email IDs that caused issues. Generic logs without concrete examples will be scrutinized.

### 3. Accuracy Metrics

Report these metrics from `evaluate.py`:
- `product_line` accuracy
- `origin_port_code` accuracy
- `destination_port_code` accuracy
- `incoterm` accuracy
- `cargo_cbm` accuracy
- `cargo_weight_kg` accuracy
- `is_dangerous` accuracy
- **Overall accuracy** (total correct fields / total fields)

### 4. Edge Cases Handled

Document at least 3 specific edge cases you encountered:
- Which email IDs had the issue?
- What was the problem?
- How did you solve it?

### 5. System Design Questions

Answer each in 2-3 paragraphs:

1. **Scale:** 10,000 emails/day, 99% processed within 5 minutes, $500/month budget. What's your architecture?

2. **Monitoring:** Extraction accuracy drops from 90% to 70% over a week. How do you detect this? Investigation process?

3. **Multilingual:** 30% emails in Mandarin, 20% in Hindi. What changes? How do you evaluate accuracy?

---

## Evaluation Criteria

| Criteria | Weight | What We Look For |
|----------|--------|------------------|
| **Accuracy** | 40% | Performance on provided + hidden test set |
| **Code Quality** | 30% | Clean code, type hints, Pydantic, error handling, graceful API timeout handling |
| **LLMOps Practices** | 20% | Prompt versioning, iteration evidence with specific examples, validation |
| **Documentation** | 10% | Clear reasoning, trade-offs explained |

### Accuracy Calculation

**Overall accuracy** = (total correct field values) / (total field values)

**Evaluated fields (9 per email):**
1. `product_line`
2. `origin_port_code`
3. `origin_port_name`
4. `destination_port_code`
5. `destination_port_name`
6. `incoterm`
7. `cargo_weight_kg`
8. `cargo_cbm`
9. `is_dangerous`

The `id` field is not evaluated (it's just an identifier).

**Comparison rules for evaluate.py:**
- String comparisons: case-insensitive, whitespace trimmed
- Float comparisons: exact match after rounding to 2 decimal places
- Null comparisons: `null` only equals `null`

### Accuracy Expectations

| Score | Rating |
|-------|--------|
| 90%+ | Exceptional |
| 80-89% | Strong |
| 70-79% | Acceptable |
| <70% | Needs improvement |

---

## Evaluation Process

1. **You submit:** GitHub repo link
2. **We review:** Code quality, documentation, approach
3. **We test:** Run your solution against **171 hidden emails** (not provided)
4. **Follow-up:** 15-20 min call to discuss your approach

### Follow-up Call Details

The call will include:
- Walk through your prompt iteration process (be ready to explain why each change was made)
- Explain a specific decision you made and trade-offs considered
- **Live modification:** Add a new extraction field or handle a new edge case we provide (to verify you wrote and understand the code)

---

## Error Handling

- **API timeouts:** Implement retry with exponential backoff (3 retries recommended)
- **Failed extractions:** If an email fails after retries, include it in `output.json` with `null` for all extracted fields (preserve the `id`). Do not skip emails.
- **Malformed inputs:** Should not crash your script

---

## Tips

1. **Start simple** — Get something working, then iterate
2. **Measure early** — Use `ground_truth.json` to check accuracy after each prompt change
3. **Temperature=0** — Required for reproducible results
4. **Document as you go** — Don't fabricate the evolution log after the fact
5. **Port not found?** — If a port isn't in the reference file, use `null` for the code
6. **evaluate.py output** — Print metrics to console in a readable format

---

## Submission

1. Push to a **public GitHub repository**
2. Verify: `pip install -r requirements.txt && python extract.py` works
3. Email link to: **hiring@taskharmony.co**
4. Subject: `Assessment Submission – [Your Name]`

---

## Questions?

Email hiring@taskharmony.co

We value clear thinking over perfect accuracy. Show us how you approach problems.
