from fastapi import FastAPI, Request, HTTPException
import os
import json
import uvicorn
from PIL import Image, ImageChops, ImageEnhance
from PIL.ExifTags import TAGS
from openai import OpenAI
import numpy as np
from iTPAEngine import DamageAnalyzer, DocumentOCRProcessor
import re
from urllib.parse import urlparse
import uuid
import tempfile
import requests
from pdf2image import convert_from_path
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut



app = FastAPI()

# Initialize Engines
url = "https://dev.ewad.me/api/ai/webhook/prediction-ready"
ocr_engine = DocumentOCRProcessor()
vision_engine = DamageAnalyzer()
DATASET_ROOT = "dataset/device_damage"
IMAGE_FOLDER = os.path.join(DATASET_ROOT, "images")
REPORT_FOLDER = os.path.join(DATASET_ROOT, "reports")
# folder name
folder_AI_report = "AI_report"

# create folder if not exists
os.makedirs(folder_AI_report, exist_ok=True)

os.makedirs(IMAGE_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# =========================
# 🔹 OpenAI Client (ENV BASED)
# =========================
client = OpenAI()

def parse_semantic_output(text):
    lines = text.split("\n")

    alignment = ""
    explanation = []

    for line in lines:
        line = line.strip()

        # Extract alignment
        if line.startswith("Semantic Alignment"):
            alignment = line.replace("Semantic Alignment:", "").strip()

        # Extract explanation points
        elif line.startswith("-"):
            explanation.append(line.replace("-", "").strip())

    return {
        "alignment": alignment,
        "explanation": explanation
    }
# =========================
# 🔹 Semantic Analysis (LLM)
# =========================
def semantic_analysis_llm(customer_reason, ai_reason):

    prompt = f"""
You are a fraud detection expert.

Compare the following two statements:

1. Customer Statement: "{customer_reason}"
2. AI Detected Cause: "{ai_reason}"

Analyze their semantic alignment.

Return output STRICTLY in this format:

Semantic Alignment: <HIGH / MEDIUM / LOW> (≈X–Y%)
Explanation:
- Point 1
- Point 2
- Point 3
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert in fraud detection and semantic reasoning."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content


# =========================
# 🔹 Extract Score from LLM Output
# =========================
def extract_semantic_score(text):
    if "HIGH" in text:
        return 0.9
    elif "MEDIUM" in text:
        return 0.6
    else:
        return 0.3


# =========================
# 🔹 ELA (Tampering Detection)
# =========================
def perform_ela(image_path, quality=90):
    original = Image.open(image_path).convert('RGB')

    temp_path = "temp_ela.jpg"
    original.save(temp_path, 'JPEG', quality=quality)

    compressed = Image.open(temp_path)

    ela_image = ImageChops.difference(original, compressed)

    extrema = ela_image.getextrema()
    max_diff = max([ex[1] for ex in extrema])

    if max_diff == 0:
        max_diff = 1

    scale = 255.0 / max_diff
    ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

    tampering_score = max_diff / 255.0

    return ela_image, tampering_score


# =========================
# 🔹 EXIF Analysis
# =========================
def check_exif(image_path):
    image = Image.open(image_path)
    exif = image._getexif()

    if not exif:
        return {"status": "No EXIF", "risk": 0.7}

    tags = {}
    for k, v in exif.items():
        tag_name = TAGS.get(k, k)
        tags[tag_name] = v

    suspicious = 0

    if "Software" in tags:
        suspicious += 1

    if "DateTimeOriginal" not in tags:
        suspicious += 1

    if "Make" not in tags:
        suspicious += 1

    risk = suspicious / 3.0

    return {
        "status": "EXIF present",
        "suspicious_flags": suspicious,
        "risk": risk,
        "tags": tags
    }


# =========================
# 🔹 Explanation Generator
# =========================
def generate_explanation(result):
    reasons = []

    if result["semantic_score"] < 0.5:
        reasons.append("Customer statement does not align with detected damage cause")

    if result["tampering_score"] > 0.8:
        reasons.append("Image shows possible tampering or manipulation")

    if result["history_flag"]:
        reasons.append("Repeated claim pattern detected")

    if result["fraud_score"] >= 3:
        reasons.append("Overall fraud probability is high")

    return "; ".join(reasons)


# =========================
# 🔹 Main Decision Engine
# =========================
def evaluate_claim(damage_report, customer_reason, image_path, historical_reasons=[]):

    analysis = damage_report.get("Damage_analysis", {}).get("description", {})

    ai_reason = analysis.get("possible_cause", "")
    risk_level = analysis.get("risk_level", "").lower()

    # -------------------------------
    # 1. Semantic Analysis (LLM)
    # -------------------------------
    semantic_text = semantic_analysis_llm(customer_reason, ai_reason)
    semantic_structured = parse_semantic_output(semantic_text)

    semantic_score = extract_semantic_score(semantic_text)

    # -------------------------------
    # 2. Image Tampering
    # -------------------------------
    _, ela_score = perform_ela(image_path)
    exif_data = check_exif(image_path)

    tamper_risk = ela_score + exif_data["risk"]

    # -------------------------------
    # 3. History Check
    # -------------------------------
    history_flag = False
    for past in historical_reasons:
        if past.lower() in customer_reason.lower():
            history_flag = True
            break

    # -------------------------------
    # 4. Fraud Score
    # -------------------------------
    fraud_score = 0

    if semantic_score < 0.5:
        fraud_score += 1

    if tamper_risk > 0.8:
        fraud_score += 1

    if history_flag:
        fraud_score += 1

    if risk_level == "high":
        fraud_score += 1

    # -------------------------------
    # 5. Final Decision
    # -------------------------------
    if fraud_score >= 3:
        verdict = "REJECTED"
        reason = "High fraud probability"
    elif fraud_score == 2:
        verdict = "REVIEW"
        reason = "Suspicious claim"
    else:
        verdict = "APPROVED"
        reason = "Valid claim"

    result = {
        "verdict": verdict,
        "reason": reason,
        "fraud_score": fraud_score,
        "semantic_analysis": semantic_structured,
        "semantic_score": semantic_score,
        "tampering_score": round(tamper_risk, 2),
        "history_flag": history_flag
    }

    result["detailed_explanation"] = generate_explanation(result)

    return result



def dupName(NameVar):
    '''
		this function is used to remove the duplicacy in the name of payload
    '''
    result = ''.join([ch for ch in NameVar if ch.isalpha() or ch.isspace() or ch == '.'])
    dup = result.split(" ")
    correctname = []
    for i in dup:
        if i in correctname:
            continue
        else:
            correctname.append(i)
    correctnameR = " ".join(correctname)

    return correctnameR

def location_check(location_name, user_country="United Arab Emirates"):
    geolocator = Nominatim(user_agent="geo_checker_app_v1")

    try:
        location = geolocator.geocode(location_name, addressdetails=True)

        if not location or 'address' not in location.raw:
            return False

        address = location.raw['address']

        # Extract values safely
        country = address.get('country', '').lower()
        country_code = address.get('country_code', '').lower()

        # Normalize user input
        user_country = user_country.lower()

        # Match either full name or ISO code
        if user_country in (country, country_code):
            return True

        return False

    except GeocoderTimedOut:
        return "Error: Geocoding service timed out"

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

def parse_date(date_str):

    if not date_str:
        return None

    date_str = str(date_str).strip()

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue

    # fallback: remove time if present
    try:
        return datetime.strptime(date_str.split(" ")[0], "%Y-%m-%d")
    except:
        return None

def validate_policy_rules(claim_data,policy_code = None):
    errors = []

    if policy_code is None:
        policy_validation = {
            "claim_type_valid": True,
            "incident_within_policy": True,
            "claim_reporting_date_within_policy_date": True,
            "report_within_5_days": True,
            "id_creation_valid": True,
            "location_valid": True,
            "errors": []
        }

        claim_type_client = str(claim_data.get("claim_type (as per client)", "")).lower()
        claim_type_policy = str(claim_data.get("Claim type (as per policy)", "")).lower()
        location = str(claim_data.get("location of incident", "")).lower()

        policy_start = claim_data.get("policy start date")
        policy_end = claim_data.get("policy end date")
        incident_date = claim_data.get("Date of incident")
        reporting_date = claim_data.get("date of claim reporting")
        id_creation_date = claim_data.get("Id creation date")
        incident_area = claim_data.get("area")

        policy_start = parse_date(policy_start)
        policy_end = parse_date(policy_end)
        incident_date = parse_date(incident_date)
        reporting_date = parse_date(reporting_date)
        id_creation_date = parse_date(id_creation_date)
        print (policy_start, policy_end, incident_date, reporting_date, id_creation_date)
        if not all([policy_start, policy_end, incident_date, reporting_date]):
            errors.append("Date format error")
            return errors

        # ---- Claim Type Validation ----
        if "combo" in claim_type_policy:
            if claim_type_client not in ["extended warranty", "accidental warranty"]:
                policy_validation["claim_type_valid"] = False
                errors.append("Claim type not covered under combo policy")
        else:
            if claim_type_client != claim_type_policy:
                policy_validation["claim_type_valid"] = False
                errors.append("Claim type does not match policy coverage")

        # ---- Policy Period Check ----
        if not(policy_start <= incident_date <= policy_end):
            policy_validation["incident_within_policy"] = False
            errors.append("Incident date outside policy period")

        if not(policy_start <= reporting_date <= policy_end):
            policy_validation["claim_reporting_date_within_policy_date"] = False
            errors.append("Claim reporting date outside policy period")

        # ---- 5 Day Rule ----
        if reporting_date > incident_date + timedelta(days=5):
            policy_validation["report_within_5_days"] = False
            errors.append("Claim reported after 5 days")
        if id_creation_date is None:
            policy_validation["id_creation_valid"] = False
            errors.append("ID creation date cannot be None")

        elif incident_date is None:
            policy_validation["id_creation_valid"] = False
            errors.append("Incident date cannot be None")

        elif id_creation_date > incident_date + timedelta(days=5):
            policy_validation["id_creation_valid"] = False
            errors.append("ID creation date beyond 5 days")
        
        # ---- Location Check ----
        if not (location_check(location) or location_check(incident_area)): 
            policy_validation["location_valid"] = False
            errors.append("Incident location must be UAE")
         
        policy_validation["errors"] = errors

        return policy_validation
    if policy_code is not None:
        pass

def calculate_match_percentage(ocr_claim_form,ocr_person_id,ocr_invoice,payload,policy_code = None):
    if policy_code is None:

        # OCR text per document
        ocr_texts = {
            "ID_DOCUMENT": build_ocr_text(ocr_person_id),
            "INVOICE": build_ocr_text(ocr_invoice),
        }

        merged_ocr_text = " ".join(ocr_texts.values())
        merged_numeric = normalize_numeric(merged_ocr_text)
        claim_data = payload.get("claim_data", {})

        fields_to_compare = {
            "invoice_number": claim_data.get("Invoice No"),
            "name": dupName(claim_data.get("Insured Name")),
            "mobile_number": claim_data.get("Insured Mobile Number"),
            "email": claim_data.get("Insured E-mail ID"),
            "device_model": claim_data.get("Device model"),
            "IMEI_N": claim_data.get("IMEI"),
            "retailer": claim_data.get("Retailer"),
            "invoice_date": claim_data.get("Invoice date"),
        }
        print ("**************************************")

        print (fields_to_compare)
        print ("&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&")

        STRICT_FIELDS = {"invoice_number","retailer","invoice_date","device_model"}

        matched_fields = {}
        strict_fail_details = {}

        match_count = 0
        total_fields = 0

        for field, expected in fields_to_compare.items():

            if not expected:
                continue

            total_fields += 1

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

        # -------------------------------
        # POLICY VALIDATION
        # -------------------------------

        policy_errors = validate_policy_rules(claim_data)

        return {
            "match_percentage": match_percentage,
            "matched_fields": matched_fields,
            "strict_fail_details": strict_fail_details,
            "matched_count": match_count,
            "total_fields": total_fields,
            "policy_validation_passed": len(policy_errors) == 0,
            "policy_validation_errors": policy_errors
        }
    if polciy_code is not None:
            pass
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
    print (payload,flush=True)

    user_id = payload.get("incident_details", {}).get("ID Image", [])
    print (user_id)
    invoice_path = payload.get("invoice_path")
    device_image_path = payload.get("image_path")
    claim_data = payload.get("claim_data", {})
    customer_reasons = claim_data.get("reasons")

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
            
    decision = evaluate_claim(
        damage_report,
        customer_reasons,
        file_path,
    )
   # add historical reasons after sometimes  

    final_verdict["final_decision"] = decision
#    final_verdict = decide_final_verdict(match_result, damage_report)

    full_report = {
            "claim_number": payload.get("claim_number"),
            "log_id": payload.get("log_id"),
            "user_id":payload.get("user_id"),
            "status": "success",
            "FMIP": "Not accessed by AI",
            "prediction_data":{
            "match_status": {
            "match_percentage": match_result.get("match_percentage"),
            "matched_count": match_result.get("matched_count"),
            "total_fields": match_result.get("total_fields"),
            "matched_fields": match_result.get("matched_fields"),
            "strict_fail_details": match_result.get("strict_fail_details"),
            "is_data_valid": match_result.get("match_percentage", 0) >= 60,

            # ADD THESE
            "policy_validation_passed": match_result.get("policy_validation_passed"),
            "policy_validation": match_result.get("policy_validation_errors")
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
    claim_no = payload.get("claim_number")
    filepath = os.path.join(folder_AI_report, f"{claim_no}.json")

    # save json
    with open(filepath, "w") as f:
        json.dump(full_report, f, indent=4, default=str)

    response = requests.post(
       url,
        json=full_report,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        timeout=30
    )

    print("Status:", response.status_code)
    print("Body:", response.text)

    return {
        "AI_response_data": full_report,
        "webhook_status_code": response.status_code,
        "webhook_response": response.json() if response.headers.get("Content-Type","").startswith("application/json") else response.text
    }
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
