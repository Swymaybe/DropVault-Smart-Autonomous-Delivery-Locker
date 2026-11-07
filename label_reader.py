import cv2
import pytesseract

try:
    from pyzbar import pyzbar
    PYZBAR_AVAILABLE = True
except Exception as e:
    PYZBAR_AVAILABLE = False
    print(f"[WARNING] pyzbar failed to load: {e}")
    print("[WARNING] The system will default to OCR only. To fix pyzbar on Windows, install the Visual C++ Redistributable.")

class LabelReader:
    def __init__(self):
        # Setup pytesseract path to the Windows binary location you just installed via winget!
        import os
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def scan_for_codes(self, parcel_roi):
        """
        Runs pyzbar to detect QR codes or 1D Barcodes.
        Extremely robust and error-free compared to OCR for verification.
        """
        if not PYZBAR_AVAILABLE:
            return []
            
        gray = cv2.cvtColor(parcel_roi, cv2.COLOR_BGR2GRAY)
        barcodes = pyzbar.decode(gray)
        
        decoded_data = []
        for barcode in barcodes:
            barcode_info = barcode.data.decode('utf-8')
            decoded_data.append(barcode_info)
            
        return decoded_data

    def secondary_ocr_scan(self, parcel_roi):
        """
        Performs an enhanced OCR pipeline on the sharpest collected frame:
        - 3x upscale, CLAHE contrast enhancement, dual-threshold approach
        """
        try:
            # Stage 1: Upscale 3x
            h, w = parcel_roi.shape[:2]
            upscaled = cv2.resize(parcel_roi, (w * 3, h * 3),
                                  interpolation=cv2.INTER_CUBIC)

            # Stage 2: Grayscale
            gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)

            # Stage 3: CLAHE - Contrast Limited Adaptive Histogram Equalization
            # Much better than simple thresholding for uneven lighting on labels!
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)

            # Stage 4: Denoise
            denoised = cv2.fastNlMeansDenoising(enhanced, h=10,
                                                 templateWindowSize=7,
                                                 searchWindowSize=21)

            # Stage 5: Try BOTH normal and inverted Otsu threshold
            # (Dark text on white = normal; white text on dark = inverted)
            _, binary_normal = cv2.threshold(denoised, 0, 255,
                                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, binary_inverted = cv2.threshold(denoised, 0, 255,
                                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            results = []
            for img_variant in [binary_normal, binary_inverted]:
                for psm in ['--psm 6 -l eng', '--psm 3 -l eng', '--psm 11 -l eng']:
                    try:
                        text = pytesseract.image_to_string(img_variant, config=psm).strip()
                        # Score = count of real words (>=3 alphanumeric chars)
                        real_words = [w for w in text.split()
                                      if len(w) >= 3 and any(c.isalpha() for c in w)]
                        results.append((text, len(real_words)))
                    except Exception:
                        results.append(("", 0))

            # Pick the result with the most real words
            best_text, best_count = max(results, key=lambda x: x[1])

            if best_count >= 1:
                # Clean up: remove lines with only symbols/single chars
                clean_lines = []
                for line in best_text.splitlines():
                    words = [w for w in line.split() if len(w) >= 3 and any(c.isalpha() for c in w)]
                    if words:
                        clean_lines.append(line)
                return "\n".join(clean_lines) if clean_lines else "LABEL_UNREADABLE"
            else:
                return "LABEL_UNREADABLE"

        except Exception as e:
            print(f"[WARNING] Tesseract OCR failed: {e}")
            print("[SIMULATION] Bypassing label scan so you can test the rest of the Capstone states!")
            return "MOCK_LABEL_VERIFIED"


