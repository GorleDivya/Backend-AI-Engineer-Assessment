# Backend / AI Engineer Assessment

## Overview

Build an LLM-powered email extraction system for freight forwarding pricing enquiries.
1. Process 50 sample emails using an LLM
2. Extract structured shipment details
3. Measure accuracy against provided ground truth
4. Document your iteration process
This project builds an LLM-powered system to automatically extract structured shipment information from freight forwarding pricing enquiry emails.
The system processes raw emails and extracts important logistics fields such as origin port, destination port, incoterm, cargo weight, cargo CBM, and dangerous goods indicators.
The extracted data is validated using Pydantic models and evaluated against a ground truth dataset to measure accuracy.

## Key Features
LLM-based email information extraction
Structured JSON output validation using Pydantic
Port code normalization using UN/LOCODE reference
Accuracy evaluation using ground truth dataset
Retry logic for API failures
Prompt iteration and optimization

## Technologies Used
- Python
- Groq API (Llama 3 model)
- Pydantic
- JSON data processing
- Prompt Engineering
## Setup Instructions

1. Clone the repository
2. Install dependencies
pip install -r requirements.txt
3.Set GROQ_API_KEY via environment variable or .env
4. Run extraction
python extract.py
5. Evaluate accuracy
python evaluate.py
How to run this program

## Files
extract.py: main pipeline (load emails → extract → validate → write output.json)
evaluate.py: computes accuracy metrics from ground_truth.json vs output.json
schemas.py: Pydantic models (input + extraction schema)
prompts.py: prompt versions (v1 → v2 → v3)
output.json: generated predictions for 50 emails

How it works
LLM extraction (Groq): Calls Groq Chat Completions with temperature=0 for deterministic outputs and asks the model to return a single JSON object for the required schema.
Validation & normalization: Pydantic enforces types, trims strings, and rounds numeric fields to 2 decimals.
Ports: Uses port_codes_reference.json to map to canonical UN/LOCODEs and canonical port names (and fuzzy-match common variants).
Rule-based safeguards:
is_dangerous detection is handled deterministically (keywords + negations).
Incoterm defaults to FOB when missing/ambiguous.
If the API call fails, the system does not skip emails—it outputs null fields (keeping the id) per spec.
Fallback mode: If GROQ_API_KEY is not set, it runs a heuristic extractor (lower accuracy) and still produces a valid output.json.

## Output Format
The system generates structured JSON output for each email.
Example:python extract.py -> writes to output.json, prints one line    

{
  "id": "EMAIL_001",
  "product_line": "pl_sea_import_lcl",
  "origin_port_code": "HKHKG",
  "destination_port_code": "INMAA",
  "incoterm": "FOB",
  "cargo_cbm": 5.0
}
LLM-powered system that extracts structured freight shipment data from pricing enquiry emails using Groq Llama models.

python evaluate.py -> reads output.json and prints the metrics 
(.venv) PS C:\Users\DELL\OneDrive\Desktop\email\th-backend-assessment> python evaluate.py
Field accuracies:
- product_line: 0/50 = 0.00%
- origin_port_code: 0/50 = 0.00%
- origin_port_name: 0/50 = 0.00%
- destination_port_code: 0/50 = 0.00%
- destination_port_name: 0/50 = 0.00%
- incoterm: 45/50 = 90.00%
- cargo_weight_kg: 16/50 = 32.00%
- cargo_cbm: 0/50 = 0.00%
- is_dangerous: 40/50 = 80.00%

Overall accuracy: 101/450 = 22.44%
