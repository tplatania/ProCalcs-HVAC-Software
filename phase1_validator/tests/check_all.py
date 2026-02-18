import fitz

plans = [
    r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\13 Five Star Bldg- Progress Drawing v6.0 for HVAC Design  01-19-26.pdf",
    r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\251216 Plan A1.1.pdf",
    r"D:\ProCalcs_HVAC_Software\phase1_validator\tests\Stone_Addition.pdf",
]

for plan in plans:
    name = plan.split("\\")[-1]
    doc = fitz.open(plan)
    print(f"\n{'='*60}")
    print(f"FILE: {name}")
    print(f"Pages: {len(doc)}")
    
    for i in range(min(3, len(doc))):
        page = doc[i]
        text = page.get_text().strip()
        annots = list(page.annots()) if page.annots() else []
        paths = page.get_drawings()
        images = page.get_images()
        
        # Count dimension-like annotations
        dim_annots = [a for a in annots if "'" in a.info.get("content", "") or '"' in a.info.get("content", "")]
        
        print(f"\n  Page {i+1}:")
        print(f"    Text chars: {len(text)}")
        print(f"    Annotations: {len(annots)} ({len(dim_annots)} with dimensions)")
        print(f"    Vector paths: {len(paths)}")
        print(f"    Embedded images: {len(images)}")
        
        if len(text) > 0:
            print(f"    Text preview: {text[:150]}")
        if dim_annots:
            dims = [a.info["content"] for a in dim_annots[:10]]
            print(f"    Dim samples: {dims}")
        
        if len(annots) > 0 or len(text) > 100:
            print(f"    --> METHOD 1 (SHX/Text extraction)")
        elif len(paths) > 100 and len(images) == 0:
            print(f"    --> METHOD 3 (High-DPI tiling - vector paths, no text)")
        elif len(images) > 0:
            print(f"    --> METHOD 3 (High-DPI tiling - scanned/raster image)")
        else:
            print(f"    --> UNKNOWN - needs investigation")
