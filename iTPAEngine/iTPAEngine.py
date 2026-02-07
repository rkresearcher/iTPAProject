from iTPAEngine import *
class DamageAnalyzer:
    def __init__(self, model="gpt-4.1-mini"):
        self.client = OpenAI()  # Automatically reads OPENAI_API_KEY
        self.model = model

    def encode_image(self, image_path):
        """Helper to encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze_screen_damage(self, image_path):
        """Analyzes device damage using the specified vision prompt."""
        base64_image = self.encode_image(image_path)

        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a device damage inspection system.\n\n"
                        "Treat the following as DAMAGE even if no cracks are visible:\n"
                        "- bending\n- warping\n- misalignment\n- deformation\n- uneven gaps\n- lid not sitting flat\n\n"
                        "Structural damage includes any deformation of the device body, "
                        "chassis, lid, hinge area, or frame caused by external force.\n\n"
                        "Analyze only what is visible in the image.\n"
                        "If deformation is visible, structural_damage MUST be true.\n"
                        "Return a structured JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze the device image carefully.\n\n"
                                "Check for:\n- cracks\n- scratches\n- dents\n- bending\n- warping\n- misalignment\n- deformation\n\n"
                                "Even if no cracks are visible, bending or deformation counts as damage.\n\n"
                                "Return a JSON with:\ndevice_type,\ndamage_list (empty only if truly no damage),\n"
                                "structural_damage (true/false),\ndamage_percentage,\nrisk_level (low/medium/high),\n"
                                "repair_solution,\npossible_cause."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            temperature=0.2
        )
        print(response.usage)
        report = json.loads(response.choices[0].message.content)
        report["image_path"] = image_path
        return report

    def process_folder(self, folder_path, output_file="Broken_Unit_Photo.json"):
        """Batch processes all images in a directory."""
        file_list = [f for f in os.listdir(folder_path)]
        for filename in file_list:
            path = os.path.join(folder_path, filename)
            print(path)
            report = self.analyze_screen_damage(path)
            print(report)
            with open(output_file, "a", encoding="utf-8") as f:
                json.dump(report, f, indent=4)

class DocumentOCRProcessor:
    def __init__(self, lang="eng"):
        self.tess_lang = lang
        self.paddle = PaddleOCR(use_angle_cls=True, lang="en")

    def pdf_to_images(self, pdf_path, first_page_only=True):
        pages = convert_from_path(pdf_path, dpi=300)
        tmp_dir = tempfile.mkdtemp()
        paths = []
        for i, page in enumerate(pages):
            if first_page_only and i > 0:
                break
            path = os.path.join(tmp_dir, f"page_{i+1}.png")
            page.save(path)
            paths.append(path)
        return paths

    def tesseract_ocr(self, img_path):
        results = []
        try:
            img = Image.open(img_path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            data = pytesseract.image_to_data(
                img,
                lang=self.tess_lang,
                output_type=pytesseract.Output.DICT
            )

            for text, conf in zip(data["text"], data["conf"]):
                if text.strip() and isinstance(conf, int) and conf > 0:
                    results.append((text.strip(), conf))

        except Exception as e:
            print(f"⚠️ Tesseract skipped {img_path}: {e}")

        return results

    def paddle_ocr(self, img_path):
        results = []
        output = self.paddle.ocr(img_path)
 
        if output and isinstance(output, list):
             data = output[0]
             for t, s in zip(data.get("rec_texts", []), data.get("rec_scores", [])):
                 if t.strip():
                     results.append((t.strip(), int(s * 100)))

        return results

    def detect_document_type(self, ocr_results):
        """
        Detect document type using OCR output only.
        """
        text = " ".join(t for t, c in ocr_results if c >= 60).upper()

        if "RESIDENT IDENTITY CARD" in text or "<<<<" in text:
            return "EMIRATES_ID"

        if "INVOICE" in text or "CCINV" in text or "EMAX" in text:
            return "INVOICE"

        if "CLAIM" in text or "SCREEN CRACKED" in text:
            return "CLAIM_FORM"

        return "UNKNOWN"

    def run_ocr(self, file_path):
        images = self.pdf_to_images(file_path) if file_path.lower().endswith(".pdf") else [file_path]

        merged = {}
        for img in images:
            for text, conf in self.tesseract_ocr(img) + self.paddle_ocr(img):
                if text not in merged or merged[text] < conf:
                    merged[text] = conf

        ocr_results = list(merged.items())
        document_type = self.detect_document_type(ocr_results)

        return {
            "document_type": document_type,
            "ocr_results": ocr_results
        }

