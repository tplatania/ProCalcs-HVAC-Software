import fitz

doc = fitz.open(r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\GT Bray floor plan.pdf")
page = doc[0]

# Check regular text
text = page.get_text().strip()
print(f"Regular text length: {len(text)} chars")
if text:
    print(f"Text preview: {text[:200]}")

# Check annotations
annots = list(page.annots()) if page.annots() else []
print(f"\nAnnotations found: {len(annots)}")
for a in annots[:10]:
    print(f"  {a.type}: {a.info.get('content', 'no content')[:80]}")

# Check if there are any embedded fonts with text
blocks = page.get_text("dict")["blocks"]
text_blocks = [b for b in blocks if b["type"] == 0]
print(f"\nText blocks: {len(text_blocks)}")
