# 📄 **README.md**

```markdown id="final_readme_001"
# 🚀 AI-Based Claim Evaluation System

An end-to-end AI-powered system for automated claim processing that integrates **document verification, damage assessment, and forensic analysis** using OCR, Computer Vision, and Large Language Models (LLMs).

---

## 📌 Overview

This system is designed for **insurance and device claim automation**, reducing manual effort while improving validation accuracy through intelligent analysis.

It combines:

- 📄 OCR-based document verification  
- 📷 AI-based damage detection  
- 🤖 LLM-based semantic reasoning  
- 🛡️ Rule-based forensic scoring  
- 📊 Policy validation  

---

## 🧠 Core Capabilities

✔ Document OCR & structured data extraction  
✔ Multi-document data matching and validation  
✔ Policy compliance verification  
✔ Device damage analysis using computer vision  
✔ Image tampering detection (ELA + EXIF)  
✔ Semantic consistency analysis using LLM  
✔ Forensic scoring engine  
✔ Automated decision output:  
→ **APPROVED / REVIEW / REJECTED**  
✔ Webhook integration for downstream systems  

---

## 🏗️ System Architecture

```

Client (JSON Request)
↓
FastAPI (/predict)
↓
OCR Engine (Documents)
↓
Data Matching Engine
↓
Policy Validation
↓
Damage Analyzer (Vision AI)
↓
Forensic Analysis Engine
↓
Decision Engine
↓
Final JSON Report
↓
Webhook (External System)

```

---

## ⚙️ Tech Stack

| Component | Technology |
|----------|----------|
| Backend | FastAPI |
| LLM | OpenAI (gpt-4o-mini) |
| OCR | DocumentOCRProcessor |
| Vision AI | DamageAnalyzer |
| Image Processing | PIL (Pillow) |
| PDF Handling | pdf2image |
| Geolocation | geopy |
| Data Processing | NumPy |
| HTTP Requests | requests |

---

## 🐍 Python Version

```

Python 3.12.3

```

---

## 📂 Project Structure

```

├── iTPAEngine/
│   ├── DamageAnalyzer/
│   └── DocumentOCRProcessor/
│
├── api_iTPAEngine.py
├── api_iTPAEngine_11_feb_send_api.py
├── api_iTPAEngine_25_mar_send_api.py
│
├── dataset/
│   └── device_damage/
│       ├── images/
│       └── reports/
│
├── AI_report/
│
├── requirements.txt
├── setup.py
└── README.md

````

> ⚠️ Note: Multiple API versions are maintained for experimentation and backward compatibility.

---

## 🚀 Installation

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd <repo-folder>
````

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variable

```bash
export OPENAI_API_KEY=your_openai_api_key
```

---

## ▶️ Run the Server

```bash
python api_iTPAEngine.py
```

OR

```bash
uvicorn api_iTPAEngine:app --host 0.0.0.0 --port 8000
```

---

## 📡 API Usage

### Endpoint

```
POST /predict
```

---

### Example Request Payload

```json
{
  "claim_number": "12345",
  "user_id": "U001",
  "claim_data": {
    "Insured Name": "John Doe",
    "Device model": "iPhone 13",
    "IMEI": "1234567890",
    "reasons": "Accidental drop",
    "upload_invoice": {
      "invoice.pdf": "https://example.com/invoice.pdf"
    },
    "upload_passport": {
      "passport.jpg": "https://example.com/passport.jpg"
    },
    "upload_claimform": {
      "form.pdf": "https://example.com/form.pdf"
    },
    "device_photo": {
      "img1.jpg": "https://example.com/device.jpg"
    }
  }
}
```

---

## 🔍 Processing Pipeline

### 🔹 1. OCR Processing

* Downloads documents from URLs
* Extracts text using OCR
* Merges results across documents

---

### 🔹 2. Data Matching

* Compares OCR-extracted data with input claim data
* Calculates match percentage

#### Matching Types:

* **Strict fields** → must match across all documents
* **Normal fields** → partial matching allowed

---

### 🔹 3. Policy Validation

Validates:

* Claim type vs policy coverage
* Policy period (start/end dates)
* Reporting within allowed timeframe (5 days)
* ID creation timing
* Incident location validation

---

### 🔹 4. Damage Analysis

* Detects:

  * Type of damage
  * Risk level
  * Possible cause

---

### 🔹 5. Forensic Analysis

#### ✔ Semantic Analysis (LLM)

Compares:

* Customer-provided reason
* AI-detected damage cause

| Alignment | Score |
| --------- | ----- |
| HIGH      | 0.9   |
| MEDIUM    | 0.6   |
| LOW       | 0.3   |

---

#### ✔ Image Tampering Detection

* Error Level Analysis (ELA)
* EXIF metadata validation

---

#### ✔ Forensic Score Calculation

| Condition                 | Score |
| ------------------------- | ----- |
| Semantic mismatch         | +1    |
| High tampering risk       | +1    |
| Repeated pattern detected | +1    |
| High damage risk          | +1    |

---

### 🔹 6. Decision Engine

| Forensic Score | Decision |
| -------------- | -------- |
| 0–1            | APPROVED |
| 2              | REVIEW   |
| 3+             | REJECTED |

---

## 📊 Output Example

```json
{
  "status": "success",
  "prediction_data": {
    "match_status": {
      "match_percentage": 82,
      "is_data_valid": true
    },
    "Damage_analysis": {
      "risk_level": "medium"
    },
    "final_decision": {
      "verdict": "REVIEW"
    }
  }
}
```

---

## 📦 Storage

| Data         | Location                       |
| ------------ | ------------------------------ |
| Images       | dataset/device_damage/images/  |
| Reports      | dataset/device_damage/reports/ |
| Final Output | AI_report/                     |

---

## 🌐 Webhook Integration

Results are sent to:

```
https://dev.ewad.me/api/ai/webhook/prediction-ready
```

---

## ⚠️ Known Issues (Important)

* ❗ `final_verdict` variable used before initialization
* ❗ No retry mechanism for webhook failures
* ❗ Limited exception handling in:

  * OCR processing
  * File downloads
* ❗ Single-image dependency in final decision

---

## 🔧 Suggested Fix (Critical Bug)

Replace:

```python
final_verdict["final_decision"] = decision
```

With:

```python
final_verdict = decision
```

---

## 🔮 Future Improvements

* Add database integration (PostgreSQL / MongoDB)
* Replace rule-based scoring with ML-based model
* Add async processing (Celery + Redis)
* Implement retry & logging system
* Build monitoring/dashboard UI
* Support multi-image aggregation

---

## 👨‍💻 Author

Developed as part of an AI-based claim forensic analysis and automation system.

---

## 📄 License

This project is intended for research and development purposes.

```

