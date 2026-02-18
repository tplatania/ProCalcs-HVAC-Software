import fitz

doc = fitz.open(r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\Del Rio Residence - Arch Set - 2026-1-15.pdf")
page = doc[1]

paths = page.get_drawings()
images = page.get_images()
print(f"Del Rio - Vector paths: {len(paths)}, Embedded images: {len(images)}")

svg = page.get_svg_image()
import re
text_elements = re.findall(r"<text[^>]*>(.*?)</text>", svg, re.DOTALL)
print(f"Del Rio - SVG text elements: {len(text_elements)}")
if text_elements:
    for t in text_elements[:10]:
        clean = t.strip()[:80]
        print(f"  {clean}")
