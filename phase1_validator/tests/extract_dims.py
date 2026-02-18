import fitz

doc = fitz.open(r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\Del Rio Residence - Arch Set - 2026-1-15.pdf")
page = doc[1]

# Get ALL text on the page, see if any dimension-like strings exist
full_text = page.get_text()
lines = [l.strip() for l in full_text.split('\n') if l.strip()]

# Look for feet-inches patterns
import re
for line in lines:
    if re.search(r"\d+'-", line) or re.search(r"\d+\u2032", line):
        print(f"FOUND: {line}")

print("\n--- Checking for dimension annotations ---")
annots = page.annots()
if annots:
    for a in annots:
        print(f"Annotation: {a.type} - {a.info}")
else:
    print("No annotations found")

print("\n--- Checking drawings/paths count ---")
paths = page.get_drawings()
print(f"Total drawing paths: {len(paths)}")
