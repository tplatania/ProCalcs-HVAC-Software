# 2026-02-18 — Plan Readability Testing Complete

## What We Tested
Tested 5 methods for reading architectural PDFs for HVAC data extraction.

## Results

| Method | Result | When to Use |
|--------|--------|-------------|
| SHX Annotation Extraction | ✅ Perfect | CAD PDFs with AutoCAD SHX text annotations |
| OCR (Tesseract) | ❌ Unreliable | Not recommended — found 2 of 15+ dims |
| High-DPI Tiling + Plan Guide | ✅ Correct | Image/vector-path PDFs with no extractable text |
| SVG Conversion | ❌ Useless | Dead end — no text in SVG output |
| PDF to DXF | ❌ Not viable | Free tools can't do it reliably |

## Decision: Two-Method System
1. Python opens PDF, checks for text/annotations
2. If found → extract everything (Method 1 bonus data)
3. Always → tile at 300 DPI, send to Opus 4.6 with Plan Reading Guide
4. AI vision does spatial reasoning (matching dims to rooms)
5. Python does math (calculations, cross-checks, validation)

## Test Plan Results
- Del Rio: CAD + SHX annotations → Method 1 works perfectly
- GT Bray: Vector paths, no text → Method 3 works with guide
- Five Star: Vector paths + images, no text → Method 3 needed
- 251216 Plan A1.1: Embedded images, no text → Method 3 needed
- Stone Addition: Vector paths, no text → Method 3 needed

**4 of 5 test plans require AI vision. SHX extraction is bonus, not primary.**

## Key Discovery
The gemini_estimate.py (1,633 lines) has useful logic patterns but the code
itself is not needed. We keep it as reference and write fresh for the validator
using Opus 4.6 instead of Gemini, built around our two proven methods.

## What's Next
Design the Phase 1 Validator spec — start in a new chat with clean context.
Reference this changelog and the Plan Reading Guide.

## Requested By
Tom
