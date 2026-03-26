from fastapi import FastAPI, Request, HTTPException
import os
import json
import uvicorn
from iTPAEngine import DamageAnalyzer, DocumentOCRProcessor
import re
from urllib.parse import urlparse
import uuid
import tempfile
import requests
from pdf2image import convert_from_path
from datetime import datetime
app = FastAPI()

# Initialize Engines
url = "http://dev.ewad.me/api/ai/webhook/prediction-ready"
ocr_engine = DocumentOCRProcessor()
vision_engine = DamageAnalyzer()
DATASET_ROOT = "dataset/device_damage"
IMAGE_FOLDER = os.path.join(DATASET_ROOT, "images")
REPORT_FOLDER = os.path.join(DATASET_ROOT, "reports")

os.makedirs(IMAGE_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

def process_uploaded_documents(doc_dict):
    for original_name, file_url in doc_dict.items():
        temp_path = None
        print ("))))))))))))))))))))))))))))))))))))))))))))))))))))",file_url)
        try:
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()

            _, ext = os.path.splitext(urlparse(file_url).path)
            if not ext:
                ext = ".pdf"

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                tmp_file.write(response.content)
                temp_path = tmp_file.name

            result = ocr_engine.run_ocr(temp_path)
            print("OCR done:", result)
            return result

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

def decide_final_verdict(match_result, gpt_damage_report):
    # Rule 1: Minimum data match
    if match_result.get("match_percentage", 0) < 60:
        return "REJECTED, Do Examine multiple fields are not matched"

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
        "name": claim_data.get("client_name"),
        "id_number": claim_data.get("client_id"),
        "serial_number": claim_data.get("imei_number"),
        "device_description": claim_data.get("claim_type"),
        "damage": claim_data.get("reason"),
        "place": claim_data.get("location_of_incident"),
        "country": claim_data.get("country"),
        "accident_date": claim_data.get("date_of_incidente"),
        "accident_hour": claim_data.get("accident_hour"),
    }
    print (fields_to_compare)
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

    # ID Document OCR
    ocr_results_person_id = process_uploaded_documents(payload.get("claim_data", {}).get("upload_passport", {}))
    
    
    # Claim form OCR
    upload_claimform = payload.get("claim_data", {}).get("upload_claimform", {})

    if upload_claimform:
        ocr_results_claim_form = process_uploaded_documents(upload_claimform)
    else:
        ocr_results_claim_form = None

    #ocr_results_person_id = process_uploaded_documents(payload.get("claim_data", {}).get("upload_claimform", {}))

    # Invoice OCR
    ocr_results_claim_invoice = process_uploaded_documents(payload.get("claim_data", {}).get("upload_invoice", {}))


# Calculate match percentage
    match_result = calculate_match_percentage(ocr_results_claim_form,ocr_results_person_id,
                                              ocr_results_claim_invoice, payload)

    print("Match Result:", match_result)

    #extracted_ocr_data = ocr_engine.extract_data(ocr_results_person_id,payload)
    match_percentage = match_result.get("match_percentage", 0)
    
    #match_percentage = calculate_match_percentage(extracted_ocr_data, mysql_record)

        # --- PHASE 2: GPT Damage Analysis ---
        # Get the full JSON report directly from your DamageAnalyzer
    
    raw_images = payload.get("claim_data", {}).get("device_photo", {})

    saved_dataset_entries = []

    for original_name, file_url in raw_images.items():
        print("Downloading image:", file_url)

        response = requests.get(file_url, timeout=30)
        response.raise_for_status()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]

        _, ext = os.path.splitext(urlparse(file_url).path)
        if not ext:
            ext = ".jpg"

        base_filename = f"{timestamp}_{unique_id}"
        file_path = os.path.join(IMAGE_FOLDER, base_filename + ext)
    
        # Save file
        with open(file_path, "wb") as f:
            f.write(response.content)

        print("Saved file:", file_path)
    
        # 🔥 Convert PDF to JPG if needed
        if ext.lower() == ".pdf":
            print("Converting PDF to image...")

            images = convert_from_path(file_path)
            converted_path = os.path.join(IMAGE_FOLDER, base_filename + ".jpg")

            images[0].save(converted_path, "JPEG")

            os.remove(file_path)  # remove original PDF
            file_path = converted_path

            print("Converted to:", file_path)

        # Run damage analysis on final image
        damage_report = vision_engine.analyze_screen_damage(file_path)

        # Save report
        report_path = os.path.join(REPORT_FOLDER, base_filename + ".json")

        with open(report_path, "w") as f:
            json.dump(damage_report, f, indent=4)

        print("Saved damage report:", report_path)

        saved_dataset_entries.append({
            "image_path": file_path,
            "report_path": report_path
        })

            # --- PHASE 3: Consolidated JSON Report ---
            # Combining both engines as per the Output block [cite: 23, 32]
    final_verdict = decide_final_verdict(match_result, damage_report)

    full_report = {
            "claim_number": payload.get("claim_number"),
            "log_id": payload.get("user_id"),
            "Status": "Success",
            "prediction_data":{
            "match_status": {
            "match_percentage": match_result.get("match_percentage"),
            "matched_count": match_result.get("matched_count"),
            "total_fields": match_result.get("total_fields"),
            "matched_fields": match_result.get("matched_fields"),
            "strict_fail_details": match_result.get("strict_fail_details"),
            "is_data_valid": match_result.get("match_percentage", 0) >= 60
        },

        "Damage_analysis": {
            "description": damage_report
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
            }
    response = requests.post(url,json=full_report,timeout=30)

    response.raise_for_status()
    return {
    "sent_data": full_report,
    "webhook_status_code": response.status_code
    }
    #except Exception as e:
     #   return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
