from fastapi import FastAPI, Request, HTTPException
import os
import json
import uvicorn
from iTPAEngine import DamageAnalyzer, DocumentOCRProcessor
import re
app = FastAPI()

# Initialize Engines
ocr_engine = DocumentOCRProcessor()
vision_engine = DamageAnalyzer()
def decide_final_verdict(match_result, gpt_damage_report):
    # Rule 1: Minimum data match
    if match_result.get("match_percentage", 0) < 60:
        return "REJECTED, Do Examine multiple filed are not matched"

    # Rule 2: Strict identity failure
    strict_failures = match_result.get("strict_fail_details", {})
    if "name" in strict_failures:
        return "Partially Reject, Do examine, Reason name is not match with one of the documents"

    # Rule 3: Damage assessment
    if isinstance(gpt_damage_report, str):
        if gpt_damage_report.lower() not in {"good", "non_structural", "minor"}:
            return "REJECTED"

    return "APPROVED"

def build_ocr_text(ocr_result):
    if not ocr_result:
        return ""

    if isinstance(ocr_result, dict):
        ocr_result = ocr_result.get("ocr_results", [])

    return " ".join(text for text, conf in ocr_result).upper()

def merge_ocr_results(*ocr_outputs):
    """
    Accepts multiple OCR outputs (dict or list format)
    Returns a single list of (text, confidence)
    """
    merged = {}

    for ocr in ocr_outputs:
        if not ocr:
            continue

        # If OCR engine returned dict {"document_type": ..., "ocr_results": [...]}
        if isinstance(ocr, dict):
            ocr = ocr.get("ocr_results", [])

        for text, conf in ocr:
            if not text:
                continue
            t = text.strip().upper()
            if t not in merged or merged[t] < conf:
                merged[t] = conf

    return [(t, c) for t, c in merged.items()]


def normalize_numeric(val):
    return re.sub(r"[^0-9]", "", val) if val else ""

def calculate_match_percentage(
    ocr_claim_form,
    ocr_person_id,
    ocr_invoice,
    payload
):
    # OCR text per document
    ocr_texts = {
        "CLAIM_FORM": build_ocr_text(ocr_claim_form),
        "ID_DOCUMENT": build_ocr_text(ocr_person_id),
        "INVOICE": build_ocr_text(ocr_invoice),
    }

    merged_ocr_text = " ".join(ocr_texts.values())
    merged_numeric = normalize_numeric(merged_ocr_text)
    claim_data = payload.get("claim_data",{})
    fields_to_compare = {
        "invoice_number": claim_data.get("invoice_number"),
        "name": claim_data.get("name"),
        "id_number": claim_data.get("id_passport_number"),
        "serial_number": claim_data.get("serial_number"),
        "device_description": claim_data.get("full_description"),
        "damage": claim_data.get("damage_description"),
        "place": claim_data.get("place"),
        "country": claim_data.get("country"),
        "accident_date": claim_data.get("accident_date"),
        "accident_hour": claim_data.get("accident_hour"),
    }

    STRICT_FIELDS = {"name"}

    matched_fields = {}
    strict_fail_details = {}

    match_count = 0
    total_fields = 0

    for field, expected in fields_to_compare.items():
        if not expected:
            continue

        total_fields += 1

        # ---- DATE / TIME ----
        if field in {"accident_date", "accident_hour"}:
            expected_norm = normalize_numeric(expected)
            matched = expected_norm in merged_numeric
            matched_fields[field] = matched
            if matched:
                match_count += 1
            continue

        # ---- STRICT FIELDS ----
        if field in STRICT_FIELDS:
            expected_norm = str(expected).upper()
            missing_docs = []

            for doc_name, doc_text in ocr_texts.items():
                if doc_text and expected_norm not in doc_text:
                    missing_docs.append(doc_name)

            matched = len(missing_docs) == 0
            matched_fields[field] = matched

            if not matched:
                strict_fail_details[field] = {
                    "matched": False,
                    "missing_in": missing_docs
                }
            else:
                match_count += 1

            continue

        # ---- NORMAL FIELDS ----
        expected_norm = str(expected).upper()
        matched = expected_norm in merged_ocr_text
        matched_fields[field] = matched
        if matched:
            match_count += 1

    match_percentage = round((match_count / total_fields) * 100, 2) if total_fields else 0

    return {
        "match_percentage": match_percentage,
        "matched_fields": matched_fields,
        "strict_fail_details": strict_fail_details,
        "matched_count": match_count,
        "total_fields": total_fields
    }

def extract_json_keys(data, parent_key=''):
    keys = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            keys.append(new_key)
            keys.extend(extract_json_keys(v, new_key))
    elif isinstance(data, list) and len(data) > 0:
        # Check first item of list for nested keys
        keys.extend(extract_json_keys(data[0], parent_key))
    return list(set(keys)) # Returns unique keywords

# Usage with your payload
    all_keywords = extract_json_keys(payload)
    print(all_keywords)
    return all_keywords
@app.post("/predict")
async def predict(request: Request):
    payload = await request.json()
    keywords = extract_json_keys(payload)
    print (payload)
    user_id = payload.get("incident_details", {}).get("ID Image", [])
    print (user_id)
    invoice_path = payload.get("invoice_path")
    device_image_path = payload.get("image_path")

    # Mock 'Data From MySQL' based on your algorithm [cite: 2]
    mysql_record = {
        "name": "JOHN DOE",
        "id_number": "784-1234-5678901-2",
        "serial_number": "SR# 987654321"
    }

#    try:
        # --- PHASE 1: OCR & Match Percentage ---
            # claim form
            # person ID
            # Invoice
    print("OCR start")

    # Claim Form OCR
    raw_claim_forms = payload.get("claim_data", {}).get("other_document",{})
    print (payload.get("claim_data", {}).get("other_document",{}))
    print (raw_claim_forms)
    try:
        claim_forms = json.loads(raw_claim_forms)
    except json.JSONDecodeError:
        claim_forms = {}
    print("PARSED:", claim_forms)
    if claim_forms:
        for original_name, stored_path in claim_forms.items():
            print("Processing file:", stored_path)

            ocr_results_claim_form = ocr_engine.run_ocr(stored_path)

            print("Claim form OCR done:", ocr_results_claim_form)


    # ID Document OCR
    raw_id_docs = payload.get("claim_data", {}).get("upload_passport")
    try:
        id_docs = json.loads(raw_id_docs)
    except json.JSONDecodeError:
        id_docs = {}
    print("PARSED:", id_docs)
    if id_docs:
        for original_name, stored_path in id_docs.items():
            print("Processing file:", stored_path)

            ocr_results_person_id = ocr_engine.run_ocr(stored_path)

            print("Claim form OCR done:", ocr_results_person_id)


    # Invoice OCR
    raw_invoices = payload.get("claim_data", {}).get("upload_invoice",{})
    try:
        invoice_ = json.loads(raw_invoices)
    except json.JSONDecodeError:
        invoice_ = {}
    print("PARSED:", invoice_)
    if invoice_:
        for original_name, stored_path in invoice_.items():
            print("Processing file:", stored_path)

            ocr_results_claim_invoice = ocr_engine.run_ocr(stored_path)

            print("Claim form OCR done:", ocr_results_claim_invoice)


# Calculate match percentage
    match_result = calculate_match_percentage(ocr_results_claim_form,ocr_results_person_id,
                                              ocr_results_claim_invoice, payload)

    print("Match Result:", match_result)

    #extracted_ocr_data = ocr_engine.extract_data(ocr_results_person_id,payload)
    match_percentage = match_result.get("match_percentage", 0)
    
    #match_percentage = calculate_match_percentage(extracted_ocr_data, mysql_record)

        # --- PHASE 2: GPT Damage Analysis ---
        # Get the full JSON report directly from your DamageAnalyzer
    raw_images = payload.get("claim_data", {}).get("device_photo",{})
    try:
        images = json.loads(raw_imagess)
    except json.JSONDecodeError:
        images = {}
    print("PARSED:", images)
    if claim_forms:
        for original_name, stored_path in images.items():
            print("Processing file:", stored_path)

            gpt_damage_report = vision_engine.analyze_screen_damage(stored_path)

            print("Claim form OCR done:", gpt_damage_report)


        # --- PHASE 3: Consolidated JSON Report ---
        # Combining both engines as per the Output block [cite: 23, 32]
    final_verdict = decide_final_verdict(match_result, gpt_damage_report)

    full_report = {
            "claim_number": payload.get("claim_number"),
            "claim_id": payload.get("claim_id"),
            "user_id": payload.get("user_id"),

        "match_status": {
            "match_percentage": match_result.get("match_percentage"),
            "matched_count": match_result.get("matched_count"),
            "total_fields": match_result.get("total_fields"),
            "matched_fields": match_result.get("matched_fields"),
            "strict_fail_details": match_result.get("strict_fail_details"),
            "is_data_valid": match_result.get("match_percentage", 0) >= 60
        },

        "Damage_analysis": {
            "description": gpt_damage_report
        },

        "final_decision": {
            "verdict": final_verdict,
            "reason": (
            "Data matched and damage acceptable"
                if final_verdict == "APPROVED"
                else "Data mismatch or strict identity failure or unacceptable damage"
            )
        }
    }

    return full_report

    #except Exception as e:
     #   return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
