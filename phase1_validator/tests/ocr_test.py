import pytesseract
from PIL import Image
import re

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

img = Image.open(r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\gt_bray_page1.png")

# Rotate 90 degrees clockwise to make text readable
img_rotated = img.rotate(-90, expand=True)

# Run OCR
data = pytesseract.image_to_data(img_rotated, output_type=pytesseract.Output.DICT)

# Dimension pattern
dim_pattern = re.compile(r"\d+['\-]\d+")

print("=== DIMENSION-LIKE TEXT (rotated) ===")
found = []
for i in range(len(data["text"])):
    txt = data["text"][i].strip()
    conf = int(data["conf"][i])
    if txt and conf > 30 and dim_pattern.search(txt):
        x, y = data["left"][i], data["top"][i]
        found.append((txt, conf, x, y))
        print(f"  {txt:25s} conf={conf:3d}  at ({x},{y})")

if not found:
    print("  No dimensions found. Showing all text with conf > 60:")
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        conf = int(data["conf"][i])
        if txt and conf > 60 and len(txt) > 1:
            x, y = data["left"][i], data["top"][i]
            print(f"  {txt:25s} conf={conf:3d}  at ({x},{y})")
