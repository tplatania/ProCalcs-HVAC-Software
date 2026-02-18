# ===============================
# Gemini Vision Multi-Pass Estimate Analysis
# Pass 1: Search for explicit sqft labels
# Pass 2: Calculate from dimensions (if no label)
# Pass 3: Verify calculation (if no label)
# Uses Gemini 3 Pro for architectural plan reading
# ===============================

import os
import base64
import json
import re
from io import BytesIO

from datetime import datetime
from pathlib import Path
import uuid

# Optional deps (safe on Cloud Run/local)
try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract  # requires tesseract binary available
except Exception:
    pytesseract = None

# Google Gemini setup (Vertex AI)
os.environ["GOOGLE_CLOUD_PROJECT"] = "psychic-medley-469413-r3"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

try:
    from google import genai
    from google.genai.types import GenerateContentConfig, Part

    GEMINI_CLIENT = genai.Client()
    GEMINI_READY = True
    print("--- Gemini Estimate: Initialized (Vertex AI - Gemini 3 Pro) ---")
except Exception as e:
    print(f"--- WARNING: Gemini Estimate initialization failed: {e} ---")
    GEMINI_READY = False
    GEMINI_CLIENT = None

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")

# Sanity check bounds
MIN_SQFT = 500
MAX_SQFT = 50000


# Audit / evidence logging
PLAN_AUDIT_ROOT = os.getenv("PLAN_AUDIT_ROOT", "/tmp/audit")
PLAN_SAVE_AUDIT = os.getenv("PLAN_SAVE_AUDIT", "1") == "1"
PLAN_OCR_EVIDENCE = os.getenv("PLAN_OCR_EVIDENCE", "1") == "1"

DIMENSION_LINE_REGEX = re.compile(
    r"(\d{1,4}\s*['′]\s*(?:-?\s*\d{1,3}(?:\s*[\- ]\s*\d{1,2}\/\d{1,2})?)?\s*(?:\"|[\u2033])?)"
)


def _ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _decode_image_bytes(img_data):
    if isinstance(img_data, str):
        try:
            return base64.b64decode(img_data)
        except Exception:
            return img_data.encode("utf-8", errors="ignore")
    return img_data


def _safe_int(v, default=0):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


def _parse_fraction(s: str) -> float:
    s = (s or "").strip()
    if not s:
        return 0.0
    if " " in s:
        whole, frac = s.split(" ", 1)
        return float(whole) + _parse_fraction(frac)
    if "/" in s:
        num, den = s.split("/", 1)
        return float(num) / float(den)
    return float(s)


def _pick_audit_dir(job_id: str) -> str:
    root = PLAN_AUDIT_ROOT
    # Handle Windows vs Linux paths
    if os.name == 'nt':  # Windows
        # Use temp directory on Windows
        import tempfile
        root = os.path.join(tempfile.gettempdir(), "audit")
    elif root and not root.startswith("/") and not re.match(r"^[A-Za-z]:\\", root):
        root = str(Path.cwd() / root)
    return _ensure_dir(str(Path(root) / job_id))


def _save_png(path: str, img_bytes: bytes) -> None:
    with open(path, "wb") as f:
        f.write(img_bytes)


def _ocr_extract_dimension_candidates(
    page_png_bytes: bytes, page_index: int, audit_dir: str, max_candidates: int = 30
) -> list:
    if not (PLAN_OCR_EVIDENCE and pytesseract and Image):
        return []
    try:
        img = Image.open(BytesIO(page_png_bytes)).convert("RGB")
    except Exception:
        return []
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    n = len(data.get("text", []))
    hits = []
    by_line = {}
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        conf = data.get("conf", ["-1"])[i]
        try:
            conf_f = float(conf)
        except Exception:
            conf_f = -1.0
        if not txt:
            continue
        key = (
            data.get("block_num", [0])[i],
            data.get("par_num", [0])[i],
            data.get("line_num", [0])[i],
        )
        by_line.setdefault(key, []).append((i, txt, conf_f))

    for items in by_line.values():
        items_sorted = sorted(items, key=lambda x: data["left"][x[0]])
        line_text = " ".join(t for _, t, _ in items_sorted)
        if not DIMENSION_LINE_REGEX.search(line_text):
            continue

        idxs = [i for i, _, _ in items_sorted]
        lefts = [data["left"][i] for i in idxs]
        tops = [data["top"][i] for i in idxs]
        rights = [data["left"][i] + data["width"][i] for i in idxs]
        bottoms = [data["top"][i] + data["height"][i] for i in idxs]
        x1, y1, x2, y2 = min(lefts), min(tops), max(rights), max(bottoms)

        confs = [c for _, _, c in items_sorted if c >= 0]
        avg_conf = round(sum(confs) / len(confs), 1) if confs else 0.0

        pad = 20
        crop_box = (
            max(0, x1 - pad),
            max(0, y1 - pad),
            min(img.width, x2 + pad),
            min(img.height, y2 + pad),
        )
        crop = img.crop(crop_box)

        crop_rel = f"page_{page_index+1:02d}/dim_line_{len(hits)+1:02d}.png"
        crop_path = str(Path(audit_dir) / crop_rel)
        _ensure_dir(str(Path(crop_path).parent))
        try:
            crop.save(crop_path)
        except Exception:
            crop_path = None

        hits.append(
            {
                "page": page_index + 1,
                "text": line_text,
                "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                "conf": avg_conf,
                "crop_path": crop_path,
            }
        )
        if len(hits) >= max_candidates:
            break

    return hits


def _apply_adjustments(gross_sqft: int, adjustments: list) -> int:
    net = int(gross_sqft or 0)
    for adj in adjustments or []:
        if not isinstance(adj, dict):
            continue
        sqft = _safe_int(adj.get("sqft", 0), 0)
        op = (adj.get("add_or_subtract") or "").lower().strip()
        if op == "subtract":
            net -= abs(sqft)
        elif op == "add":
            net += abs(sqft)
    return max(0, net)


def _compute_final_sqft(extraction: dict) -> dict:
    if not extraction or not isinstance(extraction, dict):
        return {
            "gross_sqft": None,
            "net_sqft": None,
            "details": {"reason": "no extraction"},
        }

    if isinstance(extraction.get("structures"), list) and extraction["structures"]:
        gross_total = 0
        net_total = 0
        struct_details = []
        for s in extraction["structures"]:
            if not isinstance(s, dict):
                continue
            gross = _safe_int(s.get("total_sqft") or s.get("gross_sqft") or 0, 0)
            if gross == 0 and s.get("width_feet") and s.get("length_feet"):
                try:
                    gross = int(float(s["width_feet"]) * float(s["length_feet"]))
                except Exception:
                    gross = 0
            net = _apply_adjustments(gross, s.get("adjustments"))
            gross_total += gross
            net_total += net
            struct_details.append(
                {"gross": gross, "net": net, "adjustments": s.get("adjustments", [])}
            )
        return {
            "gross_sqft": gross_total or None,
            "net_sqft": net_total or None,
            "details": {"structures": struct_details},
        }

    gross = _safe_int(
        extraction.get("total_sqft")
        or extraction.get("main_area_sqft")
        or extraction.get("sqft_value")
        or 0,
        0,
    )
    if gross == 0 and extraction.get("width_feet") and extraction.get("length_feet"):
        try:
            gross = int(
                float(extraction["width_feet"]) * float(extraction["length_feet"])
            )
        except Exception:
            gross = 0
    net = _apply_adjustments(gross, extraction.get("adjustments"))
    return {
        "gross_sqft": gross or None,
        "net_sqft": net or None,
        "details": {"adjustments": extraction.get("adjustments", [])},
    }


def is_ready():
    """Check if Gemini is available"""
    return GEMINI_READY


def _call_gemini(prompt: str, images: list = None, temperature: float = 0.2) -> str:
    """
    Make a Gemini API call with optional images.
    """
    if not GEMINI_READY:
        raise Exception("Gemini not initialized")

    try:
        content_parts = []

        # Add images first
        if images:
            for img_data in images:
                if isinstance(img_data, str):
                    img_bytes = base64.b64decode(img_data)
                else:
                    img_bytes = img_data
                content_parts.append(
                    Part.from_bytes(data=img_bytes, mime_type="image/png")
                )

        # Add text prompt
        content_parts.append(prompt)

        response = GEMINI_CLIENT.models.generate_content(
            model=GEMINI_MODEL,
            contents=content_parts,
            config=GenerateContentConfig(
                temperature=temperature, max_output_tokens=4096
            ),
        )

        return response.text.strip() if response.text else ""

    except Exception as e:
        print(f"[Gemini API] Error: {e}")
        raise


def _parse_json_response(text: str) -> dict:
    """Extract JSON from Claude response"""
    if not text:
        return {}

    try:
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            return json.loads(json_match.group())
        return {}
    except Exception as e:
        print(f"[Parse] Error: {e}")
        return {}


def _extract_dimensions_from_prose(text: str) -> dict:
    """
    Fallback when Gemini returns prose instead of JSON.
    Attempts to recover two exterior dimensions from plain text.
    Returns a Pass-2-shaped dict or {}.
    """
    if not text or not isinstance(text, str):
        return {}

    t = text.replace("×", "x")
    # Dimension token examples: 51'-4", 31'-0", 31'
    dim_token = r"(?:\d{1,4}\s*'\s*(?:[-\s]*\d{1,2}(?:[-\s]*\d/\d)?\s*\"?)?|\d{1,4}\s*')"

    # Prefer an explicit pair like "51'-4" x 31'-0""
    m = re.search(rf"({dim_token})\s*(?:x|by)\s*({dim_token})", t, flags=re.IGNORECASE)
    a = b = None
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
    else:
        # Fallback: grab first two dimension-like tokens
        toks = re.findall(dim_token, t, flags=re.IGNORECASE)
        toks = [x.strip() for x in toks if x and x.strip()]
        # de-dupe in order
        seen = set()
        dedup = []
        for tok in toks:
            if tok not in seen:
                seen.add(tok)
                dedup.append(tok)
        if len(dedup) >= 2:
            a, b = dedup[0], dedup[1]

    if not a or not b:
        return {}

    # Convert using existing normalizer
    a_ft = _normalize_dimension(a)
    b_ft = _normalize_dimension(b)

    # If one failed, try swapping
    if a_ft <= 0 or b_ft <= 0:
        a2_ft = _normalize_dimension(b)
        b2_ft = _normalize_dimension(a)
        if a2_ft > 0 and b2_ft > 0:
            a, b = b, a
            a_ft, b_ft = a2_ft, b2_ft

    if a_ft <= 0 or b_ft <= 0:
        return {}

    return {
        "total_sqft_found": False,
        "total_sqft": None,
        "exterior_width": b,
        "exterior_length": a,
        "width_feet": float(b_ft),
        "length_feet": float(a_ft),
        "source": "prose_fallback",
        "confidence": 0.55,
    }


def _parse_json_or_fallback_dimensions(response_text: str, pass_name: str) -> dict:
    """Try JSON parse first, fall back to prose dimension extraction."""
    result = _parse_json_response(response_text)
    if result:
        return result
    fb = _extract_dimensions_from_prose(response_text)
    if fb:
        print(f"[{pass_name}] JSON parse failed; recovered dimensions from prose via regex fallback.")
        return fb
    return {}


# =============================================================================
# VALIDATION GATE - Runs between AI extraction and sqft math
# =============================================================================
def _normalize_dimension(dim_str: str) -> float:
    """
    Normalize architectural dimension strings to decimal feet (supports fractions).
    Examples:
      - 51'-4"
      - 31.5'
      - 10'6-3/4"
      - 10' 6 3/4"
    """
    if not dim_str or not isinstance(dim_str, str):
        return 0.0

    s = dim_str.strip().upper()
    s = (
        s.replace("′", "'")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("″", '"')
    )
    s = re.sub(r"\s+", " ", s)

    # Decimal feet like 31.5 or 31.5'
    if re.fullmatch(r"\d+(?:\.\d+)?\s*'?", s):
        try:
            return float(s.replace("'", "").strip())
        except Exception:
            return 0.0

    m_feet = re.search(r"(\d+(?:\.\d+)?)\s*'", s)
    if not m_feet:
        return 0.0
    feet = float(m_feet.group(1))

    tail = s[m_feet.end() :].strip().replace('"', "")
    if not tail:
        return feet

    tail = tail.lstrip("-").strip()

    # Inches + optional fraction
    m_in = re.match(r"(\d+(?:\.\d+)?)\s*(?:[- ]\s*(\d+(?:\s+\d+)?\s*\/\s*\d+))?$", tail)
    if m_in:
        inches = float(m_in.group(1))
        frac = m_in.group(2)
        if frac:
            frac = re.sub(r"\s+", "", frac)
            inches += _parse_fraction(frac)
        return feet + (inches / 12.0)

    # Fraction only
    try:
        inches = _parse_fraction(re.sub(r"\s+", "", tail))
        return feet + (inches / 12.0)
    except Exception:
        return feet


# =============================================================================
# VALIDATION GATE - Runs between AI extraction and sqft math
# =============================================================================


def validate_extraction(raw_ai_output: dict, pass_name: str = "unknown") -> dict:
    """
    VALIDATION GATE: Validates AI extraction output before sqft math.

    Checks:
    1. Valid JSON structure
    2. Normalizes dimension strings to decimal feet
    3. Rejects invalid/zero dimensions
    4. Rejects absurd sqft values (< 200 or > 50,000)
    5. Rejects exclusions bigger than footprint

    Returns:
        {
            "valid": True/False,
            "normalized_data": {...},  # Only if valid
            "failure_reason": "...",   # Only if invalid
            "raw_output": {...}        # Original for debugging
        }
    """
    result = {
        "valid": False,
        "normalized_data": None,
        "failure_reason": None,
        "raw_output": raw_ai_output,
        "pass_name": pass_name,
    }

    # Check 1: Is it valid data structure?
    if not raw_ai_output or not isinstance(raw_ai_output, dict):
        result["failure_reason"] = (
            f"[{pass_name}] Invalid or empty AI output (not a dict)"
        )
        print(f"[Validation FAIL] {result['failure_reason']}")
        print(f"[Validation FAIL] Raw output: {raw_ai_output}")
        return result

    # Check 2: Does it have dimension data to validate?
    has_dimensions = any(
        key in raw_ai_output
        for key in [
            "exterior_width",
            "exterior_length",
            "width_feet",
            "length_feet",
            "rectangles",
            "total_sqft",
            "main_area_sqft",
        ]
    )

    if not has_dimensions:
        # This might be a label-only response (Pass 1), which is fine
        if raw_ai_output.get("sqft_found") is not None:
            result["valid"] = True
            result["normalized_data"] = raw_ai_output
            return result

        result["failure_reason"] = (
            f"[{pass_name}] No dimension or sqft data found in response"
        )
        print(f"[Validation FAIL] {result['failure_reason']}")
        print(f"[Validation FAIL] Raw output: {json.dumps(raw_ai_output, indent=2)}")
        return result

    # Check 3: Normalize and validate dimensions
    normalized = dict(raw_ai_output)  # Copy

    # Normalize width/length if present
    if "exterior_width" in raw_ai_output:
        width_str = raw_ai_output.get("exterior_width", "")
        length_str = raw_ai_output.get("exterior_length", "")

        width_ft = _normalize_dimension(width_str)
        length_ft = _normalize_dimension(length_str)

        # Also check if they provided pre-converted values
        if width_ft == 0 and "width_feet" in raw_ai_output:
            try:
                width_ft = float(raw_ai_output["width_feet"])
            except (ValueError, TypeError):
                pass

        if length_ft == 0 and "length_feet" in raw_ai_output:
            try:
                length_ft = float(raw_ai_output["length_feet"])
            except (ValueError, TypeError):
                pass

        # Reject zero/invalid dimensions
        if width_ft <= 0 or length_ft <= 0:
            result["failure_reason"] = (
                f"[{pass_name}] Invalid dimensions: width='{width_str}'→{width_ft}ft, length='{length_str}'→{length_ft}ft"
            )
            print(f"[Validation FAIL] {result['failure_reason']}")
            print(
                f"[Validation FAIL] Raw output: {json.dumps(raw_ai_output, indent=2)}"
            )
            return result

        normalized["width_feet"] = width_ft
        normalized["length_feet"] = length_ft
        normalized["calculated_main_sqft"] = round(width_ft * length_ft)

    # Check 4: Validate total sqft
    total_sqft = raw_ai_output.get("total_sqft") or raw_ai_output.get("main_area_sqft")
    if total_sqft:
        try:
            total_sqft = int(float(str(total_sqft).replace(",", "")))
        except (ValueError, TypeError):
            result["failure_reason"] = (
                f"[{pass_name}] Cannot parse total_sqft: {raw_ai_output.get('total_sqft')}"
            )
            print(f"[Validation FAIL] {result['failure_reason']}")
            return result

        # Sanity check
        if total_sqft < 200:
            result["failure_reason"] = (
                f"[{pass_name}] Sqft too small: {total_sqft} (min 200)"
            )
            print(f"[Validation FAIL] {result['failure_reason']}")
            print(
                f"[Validation FAIL] Raw output: {json.dumps(raw_ai_output, indent=2)}"
            )
            return result

        if total_sqft > 50000:
            result["failure_reason"] = (
                f"[{pass_name}] Sqft too large: {total_sqft} (max 50,000)"
            )
            print(f"[Validation FAIL] {result['failure_reason']}")
            print(
                f"[Validation FAIL] Raw output: {json.dumps(raw_ai_output, indent=2)}"
            )
            return result

        normalized["total_sqft"] = total_sqft

    # Check 5: Validate adjustments/exclusions
    adjustments = raw_ai_output.get("adjustments", [])
    footprint_sqft = normalized.get("calculated_main_sqft") or normalized.get(
        "total_sqft", 0
    )

    for adj in adjustments:
        if isinstance(adj, dict):
            adj_sqft = adj.get("sqft", 0)
            try:
                adj_sqft = abs(int(float(str(adj_sqft).replace(",", ""))))
            except (ValueError, TypeError):
                continue

            # Exclusion bigger than footprint?
            if adj.get("add_or_subtract") == "subtract" and adj_sqft > footprint_sqft:
                result["failure_reason"] = (
                    f"[{pass_name}] Exclusion ({adj_sqft} sqft) larger than footprint ({footprint_sqft} sqft)"
                )
                print(f"[Validation FAIL] {result['failure_reason']}")
                print(
                    f"[Validation FAIL] Raw output: {json.dumps(raw_ai_output, indent=2)}"
                )
                return result

    # All checks passed
    result["valid"] = True
    result["normalized_data"] = normalized
    print(f"[Validation PASS] {pass_name}: {normalized.get('total_sqft', 'N/A')} sqft")
    return result


# =============================================================================
# EMAIL CONTEXT EXTRACTION
# =============================================================================
def extract_email_context(email_body: str, email_subject: str = "") -> dict:
    """Parse email for hints about the project."""
    context = {
        "unconditioned_spaces": [],
        "multiple_structures": False,
        "is_rush": False,
        "raw_hints": [],
    }

    if not email_body:
        return context

    email_lower = (email_body + " " + email_subject).lower()

    # Detect unconditioned space mentions
    unconditioned_keywords = [
        "unconditioned",
        "unheated",
        "not conditioned",
        "storage room",
        "will not get hvac",
        "won't get hvac",
        "no hvac",
        "no ac",
        "not heated",
        "house chemicals",
        "mechanical room",
    ]
    for kw in unconditioned_keywords:
        if kw in email_lower:
            context["raw_hints"].append(f"Found: '{kw}'")

    # Multiple structures
    multi_keywords = [
        "second building",
        "two buildings",
        "guest house",
        "mother-in-law",
        "adu",
        "detached",
        "separate structure",
    ]
    for kw in multi_keywords:
        if kw in email_lower:
            context["multiple_structures"] = True
            context["raw_hints"].append(f"Multiple structures: '{kw}'")
            break

    # Rush detection
    rush_keywords = ["rush", "urgent", "asap", "expedite", "priority"]
    for kw in rush_keywords:
        if kw in email_lower:
            context["is_rush"] = True
            break

    return context


# =============================================================================
# PASS 1: Search for Explicit Square Footage Labels
# =============================================================================
def vision_pass_1_find_sqft_label(images: list) -> dict:
    """
    SLOW, THOROUGH search for explicit sqft labels on plans.
    Look for: LIVING AREA, CONDITIONED AREA, TOTAL SF, GROSS BUILDING AREA, etc.
    """
    prompt = """You are analyzing architectural floor plans to find EXPLICIT square footage labels.

SEARCH SLOWLY AND THOROUGHLY through ALL pages for any of these labels:
- "LIVING AREA: X,XXX SF" or "LIVING: X,XXX"
- "CONDITIONED AREA: X,XXX SF"
- "HEATED AREA: X,XXX SF"  
- "TOTAL LIVING: X,XXX SF"
- "MAIN LIVING AREA: X,XXX SF"
- "GROSS BUILDING AREA: X,XXX SF" (commercial)
- "TOTAL AREA: X,XXX SF"
- Any variation with S.F., SQ FT, SQFT, SF

CHECK THESE LOCATIONS:
1. Title block (usually right side, may be rotated 90°)
2. Area calculation box/table
3. Room schedule
4. Cover sheet summary
5. Near the building outline/footprint
6. Bottom of page notations

IMPORTANT: Only report a sqft value if you see an EXPLICIT LABEL with a number.
Do NOT calculate or estimate - just find existing labels.

Return JSON:
{
    "sqft_found": true/false,
    "sqft_value": 2723 (number only, no commas),
    "label_text": "MAIN LIVING AREA: 2,723 S.F." (exact text you found),
    "label_location": "title block page 1" or "area table page 2",
    "is_conditioned": true/false (is this conditioned/heated area vs gross?),
    "confidence": 0.95 (how confident are you this is accurate?)
}

If NO explicit label found, return:
{
    "sqft_found": false,
    "sqft_value": null,
    "label_text": null,
    "confidence": 0
}"""

    print("[Pass 1] Searching for explicit sqft labels...")
    response = _call_gemini(prompt, images, temperature=0.1)
    print(f"[Pass 1] Raw response: {response[:500] if response else 'EMPTY'}")
    result = _parse_json_response(response)

    # Validate result
    if result.get("sqft_found") and result.get("sqft_value"):
        sqft = result["sqft_value"]
        if isinstance(sqft, str):
            sqft = int(sqft.replace(",", "").replace(".", ""))

        # Sanity check
        if MIN_SQFT <= sqft <= MAX_SQFT:
            result["sqft_value"] = sqft
            result["passed_sanity"] = True
            print(f"[Pass 1] Found label: {sqft} sqft - '{result.get('label_text')}'")
        else:
            print(
                f"[Pass 1] Found {sqft} but failed sanity check ({MIN_SQFT}-{MAX_SQFT})"
            )
            result["sqft_found"] = False
            result["passed_sanity"] = False

    return result


# =============================================================================
# STRUCTURE DETECTION: Find ALL buildings/structures on plans
# =============================================================================
def vision_detect_all_structures(images: list) -> dict:
    """
    Detect ALL structures on the architectural plans.
    Returns list of structures with names and square footage.
    """
    prompt = """You are analyzing architectural floor plans to find ALL STRUCTURES on the property.

Look for MULTIPLE BUILDINGS such as:
- Main House / Primary Residence
- ADU (Accessory Dwelling Unit) / Guest House / Casita / In-Law Suite
- Detached Garage / Carport
- Pool House / Cabana
- Workshop / Studio / Office Building
- Barn / Storage Building
- Any other separate structure

For EACH structure found, look for:
1. Explicit square footage labels (LIVING AREA, CONDITIONED AREA, TOTAL SF, etc.)
2. Building name/label identifying what it is
3. Whether it appears to be conditioned (heated/cooled) space

IMPORTANT: 
- The MAIN HOUSE is always the largest residential structure
- ADUs are typically smaller separate living units (400-1200 sqft)
- Garages are typically 200-800 sqft and usually NOT conditioned
- Only report structures you can clearly identify with sqft labels or dimensions

Return JSON:
{
    "structures_found": true/false,
    "structures": [
        {
            "name": "Main House",
            "sqft": 2450,
            "label_text": "LIVING AREA: 2,450 S.F.",
            "is_conditioned": true,
            "is_primary": true,
            "confidence": 0.95
        },
        {
            "name": "ADU",
            "sqft": 680,
            "label_text": "ADU LIVING: 680 SF",
            "is_conditioned": true,
            "is_primary": false,
            "confidence": 0.90
        },
        {
            "name": "Detached Garage",
            "sqft": 520,
            "label_text": "GARAGE: 520 SF",
            "is_conditioned": false,
            "is_primary": false,
            "confidence": 0.85
        }
    ],
    "total_conditioned_sqft": 3130,
    "notes": "ADU appears to be a separate guest house behind main residence"
}

If only ONE structure (main building) found:
{
    "structures_found": true,
    "structures": [
        {
            "name": "Main House",
            "sqft": 2450,
            "label_text": "LIVING AREA: 2,450 S.F.",
            "is_conditioned": true,
            "is_primary": true,
            "confidence": 0.95
        }
    ],
    "total_conditioned_sqft": 2450,
    "notes": null
}

If NO structures/sqft found:
{
    "structures_found": false,
    "structures": [],
    "total_conditioned_sqft": null,
    "notes": "Could not find explicit square footage labels"
}"""

    print("[Structure Detection] Scanning for all structures...")
    response = _call_gemini(prompt, images, temperature=0.1)
    print(f"[Structure Detection] Raw response: {response[:500] if response else 'EMPTY'}")
    result = _parse_json_response(response)

    # Validate and clean up structures
    if result.get("structures_found") and result.get("structures"):
        valid_structures = []
        for struct in result["structures"]:
            if isinstance(struct, dict) and struct.get("sqft"):
                sqft = struct["sqft"]
                if isinstance(sqft, str):
                    sqft = int(sqft.replace(",", "").replace(".", ""))
                # Sanity check individual structure
                if 100 <= sqft <= MAX_SQFT:
                    struct["sqft"] = sqft
                    valid_structures.append(struct)
                    print(f"[Structure Detection] Found: {struct.get('name')} = {sqft} sqft")
        
        result["structures"] = valid_structures
        result["structures_found"] = len(valid_structures) > 0
        
        # Recalculate total conditioned
        total_cond = sum(s["sqft"] for s in valid_structures if s.get("is_conditioned", True))
        result["total_conditioned_sqft"] = total_cond if total_cond > 0 else None

    return result


# =============================================================================
# PASS 2: Extract Square Footage - Simple Approach
# =============================================================================
def vision_pass_2_calculate_from_dimensions(images: list, email_context: dict) -> dict:
    """
    Simple extraction - look for TOTAL sqft or exterior dimensions.
    Python does the math.
    """
    prompt = """Look at these floor plans and find the TOTAL CONDITIONED SQUARE FOOTAGE.

CHECK FOR:
1. A label like "TOTAL: X,XXX SF" or "CONDITIONED AREA: X,XXX SF" or "GROSS AREA: X,XXX SF"
2. If no total label, find the OVERALL EXTERIOR DIMENSIONS of the building (e.g., "110'-0" x 60'-0"")

Return JSON:
{
    "total_sqft_found": true or false,
    "total_sqft": 6600,
    "exterior_width": "110'-0\"",
    "exterior_length": "60'-0\"",
    "width_feet": 110.0,
    "length_feet": 60.0,
    "source": "label" or "dimensions",
    "confidence": 0.8
}

If you find a total label, use that. If not, provide the exterior dimensions and I will calculate."""

    print("[Pass 2] Simple sqft extraction...")
    response = _call_gemini(prompt, images[:3], temperature=0.2)  # Only 3 images
    print(f"[Pass 2] Raw response: {response[:500] if response else 'EMPTY'}")

    if not response or response.strip() == "":
        return {
            "passed_sanity": False,
            "needs_review": True,
            "validation_failure": "Empty response from AI",
        }

    result = _parse_json_or_fallback_dimensions(response, "Pass 2")

    if not result:
        return {
            "passed_sanity": False,
            "needs_review": True,
            "validation_failure": "Could not parse AI response",
        }

    # Check if total sqft was found directly
    total_sqft = 0

    if result.get("total_sqft_found") and result.get("total_sqft"):
        total_sqft = int(result["total_sqft"])
        result["calculation_method"] = "ai_found_label"
        print(f"[Pass 2] AI found total: {total_sqft} sqft")

    # Otherwise calculate from dimensions
    elif result.get("width_feet") and result.get("length_feet"):
        width = float(result["width_feet"])
        length = float(result["length_feet"])
        if width > 0 and length > 0:
            total_sqft = int(width * length)
            result["calculation_method"] = "python_dimension_calc"
            print(f"[Pass 2] Python calc: {width} x {length} = {total_sqft} sqft")

    # Try normalizing dimension strings if feet values missing
    elif result.get("exterior_width") and result.get("exterior_length"):
        width = _normalize_dimension(result["exterior_width"])
        length = _normalize_dimension(result["exterior_length"])
        if width > 0 and length > 0:
            total_sqft = int(width * length)
            result["width_feet"] = width
            result["length_feet"] = length
            result["calculation_method"] = "python_dimension_calc"
            print(
                f"[Pass 2] Python calc (normalized): {width} x {length} = {total_sqft} sqft"
            )

    # Validation
    if total_sqft < MIN_SQFT:
        result["passed_sanity"] = False
        result["needs_review"] = True
        result["validation_failure"] = (
            f"Total sqft {total_sqft} below minimum {MIN_SQFT}"
        )
        result["total_sqft"] = total_sqft
        print(f"[Pass 2] FAILED: {result['validation_failure']}")
        return result

    if total_sqft > MAX_SQFT:
        result["passed_sanity"] = False
        result["needs_review"] = True
        result["validation_failure"] = (
            f"Total sqft {total_sqft} above maximum {MAX_SQFT}"
        )
        result["total_sqft"] = total_sqft
        print(f"[Pass 2] FAILED: {result['validation_failure']}")
        return result

    result["total_sqft"] = total_sqft
    result["passed_sanity"] = True
    print(
        f"[Pass 2] Success: {total_sqft} sqft ({result.get('calculation_method', 'unknown')})"
    )
    return result


# =============================================================================
# PASS 3: Verify - Second attempt with different prompt
# =============================================================================
def vision_pass_3_verify_calculation(images: list) -> dict:
    """
    Simple verification pass - different wording, same goal.
    """
    prompt = """Find the building's TOTAL SQUARE FOOTAGE from these architectural plans.

Look for:
1. An area summary or schedule showing total sqft
2. The main exterior dimensions of the building footprint

Return JSON only:
{
    "sqft": 6600,
    "width": "110'-0\"",
    "length": "60'-0\"",
    "method": "found_label" or "from_dimensions"
}"""

    print("[Pass 3] Verification pass...")
    response = _call_gemini(prompt, images[:2], temperature=0.3)  # Only 2 images
    print(f"[Pass 3] Raw response: {response[:500] if response else 'EMPTY'}")

    if not response or response.strip() == "":
        return {
            "passed_sanity": False,
            "needs_review": True,
            "validation_failure": "Empty response from AI",
        }

    result = _parse_json_or_fallback_dimensions(response, "Pass 3")

    if not result:
        return {
            "passed_sanity": False,
            "needs_review": True,
            "validation_failure": "Could not parse AI response",
        }

    # If we used the prose fallback (Pass 2-style keys), map into Pass 3 schema
    if "width" not in result and result.get("exterior_width"):
        result["width"] = result.get("exterior_width")
    if "length" not in result and result.get("exterior_length"):
        result["length"] = result.get("exterior_length")

    total_sqft = 0

    # Direct sqft value
    if result.get("sqft"):
        try:
            total_sqft = int(result["sqft"])
            result["calculation_method"] = "ai_provided"
            print(f"[Pass 3] AI provided: {total_sqft} sqft")
        except (ValueError, TypeError):
            pass

    # Calculate from dimensions if no sqft
    if total_sqft == 0 and result.get("width") and result.get("length"):
        width = _normalize_dimension(result["width"])
        length = _normalize_dimension(result["length"])
        if width > 0 and length > 0:
            total_sqft = int(width * length)
            result["calculation_method"] = "python_calc"
            print(f"[Pass 3] Python calc: {width} x {length} = {total_sqft} sqft")

    # Validation
    if total_sqft < MIN_SQFT:
        result["passed_sanity"] = False
        result["needs_review"] = True
        result["validation_failure"] = f"Sqft {total_sqft} below minimum"
        result["total_sqft"] = total_sqft
        return result

    if total_sqft > MAX_SQFT:
        result["passed_sanity"] = False
        result["needs_review"] = True
        result["validation_failure"] = f"Sqft {total_sqft} above maximum"
        result["total_sqft"] = total_sqft
        return result

    result["total_sqft"] = total_sqft
    result["passed_sanity"] = True
    print(f"[Pass 3] Success: {total_sqft} sqft")
    return result


# =============================================================================
# Compare Pass 2 and Pass 3 Results
# =============================================================================
def compare_calculation_passes(pass2: dict, pass3: dict) -> dict:
    """
    Compare two independent calculations.
    If within 10%, use average. If not, flag for review.
    Returns NEEDS_REVIEW if validation failed on either pass.
    """
    sqft2 = pass2.get("total_sqft")
    sqft3 = pass3.get("total_sqft")
    
    # If Pass 2 succeeded but Pass 3 returned empty/failed, trust Pass 2
    if sqft2 and pass2.get("passed_sanity") and (not sqft3 or pass3.get("needs_review")):
        print(f"[Compare] Pass 2 succeeded ({sqft2}), Pass 3 failed/empty - using Pass 2")
        return {
            "match": True,
            "pass2_sqft": sqft2,
            "pass3_sqft": sqft3,
            "final_sqft": sqft2,
            "flag_for_review": False,
            "reason": "Pass 2 succeeded, Pass 3 empty - trusting Pass 2"
        }
    
    # Check for validation failures on both
    if pass2.get("needs_review") and pass3.get("needs_review"):
        failure_reasons = []
        if pass2.get("validation_failure"):
            failure_reasons.append(f"Pass2: {pass2['validation_failure']}")
        if pass3.get("validation_failure"):
            failure_reasons.append(f"Pass3: {pass3['validation_failure']}")

        return {
            "match": False,
            "final_sqft": None,
            "flag_for_review": True,
            "needs_review": "NEEDS_REVIEW",
            "reason": (
                " | ".join(failure_reasons) if failure_reasons else "Validation failed"
            ),
        }

    if not sqft2 or not sqft3:
        return {
            "match": False,
            "final_sqft": sqft2 or sqft3,
            "flag_for_review": True,
            "reason": "One or both calculations failed",
        }

    # Calculate difference percentage
    diff = abs(sqft2 - sqft3)
    avg = (sqft2 + sqft3) / 2
    diff_percent = (diff / avg) * 100 if avg > 0 else 100

    if diff_percent <= 10:
        # Close enough - use average
        final = int(round(avg))
        print(
            f"[Compare] Pass 2: {sqft2}, Pass 3: {sqft3}, Diff: {diff_percent:.1f}% - MATCH, using {final}"
        )
        return {
            "match": True,
            "pass2_sqft": sqft2,
            "pass3_sqft": sqft3,
            "difference_percent": round(diff_percent, 1),
            "final_sqft": final,
            "flag_for_review": False,
            "reason": "Calculations within 10%",
        }
    else:
        # Too different - flag for human review
        print(
            f"[Compare] Pass 2: {sqft2}, Pass 3: {sqft3}, Diff: {diff_percent:.1f}% - MISMATCH"
        )
        return {
            "match": False,
            "pass2_sqft": sqft2,
            "pass3_sqft": sqft3,
            "difference_percent": round(diff_percent, 1),
            "final_sqft": None,
            "flag_for_review": True,
            "reason": f"Calculations differ by {diff_percent:.1f}% - needs human review",
        }


# =============================================================================
# CLAUDE VISION: Project Metadata Extraction
# =============================================================================
def extract_project_metadata(
    images: list, email_body: str = "", email_from: str = "", email_subject: str = ""
) -> dict:
    """
    Use Claude Vision to extract project metadata from title block.
    """
    prompt = f"""Analyze this architectural floor plan and extract project information.

TITLE BLOCK: Usually on the right side, may be rotated 90°. Contains project name, address, client info.

Extract:
1. Project Name - from title block
2. Project Address - street, city, state, zip
3. Project Type:
   - "RNC" = New residential construction
   - "RREN" = Residential renovation/addition
   - "CNC" = New commercial construction  
   - "CREN" = Commercial renovation/addition
   Look for words like "EXISTING", "NEW", "ADDITION", "RENOVATION"
4. Number of stories (count floor levels shown)
5. Is this commercial? (maintenance building, office, retail = yes)

CLIENT NAME: Use the email sender name.
Email From: {email_from}
Email Subject: {email_subject}

Return JSON only:
{{
    "client_name": "from email sender",
    "project_name": "from title block",
    "project_address": "full address",
    "city": "city name",
    "state": "2-letter code",
    "zip": "zip code",
    "project_type": "RNC/RREN/CNC/CREN",
    "is_commercial": true/false,
    "num_stories": 1,
    "confidence": 0.9
}}"""

    print("[Metadata] Extracting project info...")
    response = _call_gemini(prompt, images)
    result = _parse_json_response(response)

    # Extract client name from email if not found
    if not result.get("client_name") and email_from:
        name_match = re.match(r"^([^<]+)", email_from)
        if name_match:
            result["client_name"] = name_match.group(1).strip()

    return result


# =============================================================================
# CLAUDE VISION: Complexity Detection
# =============================================================================
def detect_complexity(images: list, project_info: dict, email_body: str = "") -> dict:
    """
    Use Claude Vision to detect complexity factors affecting pricing.
    """
    project_type = project_info.get("project_type", "RNC")
    state = project_info.get("state", "")
    num_stories = project_info.get("num_stories", 1)

    prompt = f"""Analyze this floor plan for complexity factors.

PROJECT INFO:
- Type: {project_type}
- State: {state}  
- Stories: {num_stories}

DETECT THESE FACTORS:
1. Hand-drawn plans (vs clean CAD lines)
2. Specialty space - look for: salon, spa, restaurant, kitchen, medical, dental
3. Multiple HVAC systems likely needed (split floor plan, 2+ stories, large building)
4. 30+ occupants (commercial only)

EMAIL (check for add-ons):
{email_body[:1500]}

Return JSON:
{{
    "complexity_indicators": {{
        "rren_cren_addition": {{"detected": {"true" if project_type in ["RREN", "CREN"] else "false"}, "points": 1}},
        "hand_drawn_plans": {{"detected": false, "points": 1}},
        "title_24_or_washington": {{"detected": {"true" if state in ["CA", "WA"] else "false"}, "points": 1}},
        "specialty_space": {{"detected": false, "points": 3, "type": null}},
        "high_occupancy_30_plus": {{"detected": false, "points": 2}},
        "multistory_ductwork": {{"detected": {"true" if num_stories >= 2 else "false"}, "points": 1}}
    }},
    "addons_detected": {{
        "exhaust_fan_ducting": false,
        "refrigerant_piping": false,
        "mini_split": false,
        "erv_dehumidifier": false,
        "rush_fee": false
    }},
    "confidence": 0.8
}}"""

    print("[Complexity] Detecting factors...")
    response = _call_gemini(prompt, images)
    return _parse_json_response(response)


# =============================================================================
# PRICING RULES
# =============================================================================
PROCALCS_RULES = {
    "base_prices": {
        "RNC": {
            "manual_d": 165,
            "manual_j": 75,
            "manual_s": 350,
            "basic": 325,
            "basic_plus_mj": 400,
        },
        "RREN": {"manual_d": 195, "basic": 375},
        "CNC": {"manual_d": 250, "basic": 450},
        "CREN": {"manual_d": 275, "basic": 500},
    },
    "sqft_tiers": [
        {"max_sqft": 2000, "multiplier": 1.0},
        {"max_sqft": 3500, "multiplier": 1.15},
        {"max_sqft": 5000, "multiplier": 1.30},
        {"max_sqft": 7500, "multiplier": 1.50},
        {"max_sqft": 999999, "multiplier": 1.75},
    ],
    "complexity_adders": {
        "hand_drawn_plans": 50,
        "specialty_space": 75,
        "title_24_or_washington": 100,
        "high_occupancy_30_plus": 150,
        "multistory_intermediate_ductwork": 75,
        "multiple_systems_per_extra": 150,
    },
}


def calculate_quote(
    sqft: int, project_type: str, complexity: dict, package: str = "basic"
) -> dict:
    """Deterministic price calculation using ProCalcs rules."""
    base_prices = PROCALCS_RULES["base_prices"].get(
        project_type, PROCALCS_RULES["base_prices"]["RNC"]
    )
    base = base_prices.get(package, base_prices.get("basic", 325))

    # Apply sqft multiplier
    multiplier = 1.0
    for tier in PROCALCS_RULES["sqft_tiers"]:
        if sqft <= tier["max_sqft"]:
            multiplier = tier["multiplier"]
            break

    subtotal = base * multiplier

    # Apply complexity adders
    adders = []
    indicators = complexity.get("complexity_indicators", {})

    for key, adder_amount in PROCALCS_RULES["complexity_adders"].items():
        indicator = indicators.get(key, {})
        if isinstance(indicator, dict) and indicator.get("detected"):
            adders.append(
                {"name": key.replace("_", " ").title(), "amount": adder_amount}
            )

    adder_total = sum(a["amount"] for a in adders)

    return {
        "base_price": round(base),
        "sqft_multiplier": multiplier,
        "subtotal": round(subtotal),
        "complexity_adders": adders,
        "adder_total": round(adder_total),
        "total": round(subtotal + adder_total),
        "package": package,
    }


# =============================================================================
# MAIN: Run Full Analysis Pipeline
# =============================================================================
def analyze_estimate(
    pdf_images: list,
    pdf_raw_bytes: list = None,
    email_body: str = "",
    email_from: str = "",
    email_subject: str = "",
) -> dict:
    """
    Run the multi-pass estimate analysis pipeline.

    NEW FLOW:
    1. Email context extraction
    2. Pass 1: Search for explicit sqft label (Claude Vision)
    3. If no label → Pass 2: Calculate from dimensions
    4. If no label → Pass 3: Verify calculation
    5. Compare Pass 2 & 3 → Match = use, Mismatch = flag
    6. Metadata extraction
    7. Complexity detection
    8. Quote calculation
    """
    if not GEMINI_READY:
        return {"error": "Gemini AI not available", "success": False}

    if not pdf_images:
        return {"error": "No plan images provided", "success": False}

    results = {
        "success": True,
        "method": "claude_vision_multipass",
        "flag_for_review": False,
        "flag_reason": None,
        "passes": {},
    }

    # Audit folder (per request/job)
    job_id = str(uuid.uuid4())
    results["job_id"] = job_id
    results["audit"] = {
        "enabled": PLAN_SAVE_AUDIT,
        "root": PLAN_AUDIT_ROOT,
        "dir": None,
    }
    audit_dir = None
    if PLAN_SAVE_AUDIT:
        audit_dir = _pick_audit_dir(job_id)
        results["audit"]["dir"] = audit_dir

    try:
        # Get image data (first 4 pages for sqft, first 3 for metadata)
        images = [img["data"] for img in pdf_images[:4]]

        # Save page renders for debugging (and optionally OCR evidence)
        if audit_dir:
            for i, img_data in enumerate(images):
                try:
                    b = _decode_image_bytes(img_data)
                    page_path = str(Path(audit_dir) / f"page_{i+1:02d}" / "page.png")
                    _ensure_dir(str(Path(page_path).parent))
                    _save_png(page_path, b)
                except Exception:
                    pass

            if PLAN_OCR_EVIDENCE:
                ocr_evidence = {}
                for i, img_data in enumerate(images):
                    try:
                        b = _decode_image_bytes(img_data)
                        ocr_evidence[f"page_{i+1}"] = _ocr_extract_dimension_candidates(
                            b, i, audit_dir
                        )
                    except Exception:
                        ocr_evidence[f"page_{i+1}"] = []
                results["ocr_evidence"] = ocr_evidence

        # =================================================================
        # STEP 1: EMAIL CONTEXT
        # =================================================================
        print("[Step 1] Extracting email context...")
        email_context = extract_email_context(email_body, email_subject)
        results["email_context"] = email_context

        # =================================================================
        # STEP 2: PASS 1 - Find Explicit SqFt Label
        # =================================================================
        print("[Step 2] Pass 1 - Searching for sqft label...")
        pass1 = vision_pass_1_find_sqft_label(images)
        results["passes"]["pass1_label_search"] = pass1

        # =================================================================
        # STEP 2.5: STRUCTURE DETECTION - Find ALL buildings
        # =================================================================
        print("[Step 2.5] Detecting all structures...")
        structures_result = vision_detect_all_structures(images)
        results["passes"]["structure_detection"] = structures_result
        detected_structures = structures_result.get("structures", [])

        final_sqft = None
        sqft_source = None

        if pass1.get("sqft_found") and pass1.get("passed_sanity"):
            # Found explicit label - USE IT
            final_sqft = pass1["sqft_value"]
            sqft_source = "explicit_label"
            print(f"[Result] Using explicit label: {final_sqft} sqft")
        else:
            # =============================================================
            # STEP 3: PASS 2 - Calculate from Dimensions
            # =============================================================
            print("[Step 3] Pass 2 - Calculating from dimensions...")
            pass2 = vision_pass_2_calculate_from_dimensions(images, email_context)
            results["passes"]["pass2_dimension_calc"] = pass2

            # =============================================================
            # STEP 4: PASS 3 - Verify Calculation
            # =============================================================
            print("[Step 4] Pass 3 - Verification calculation...")
            pass3 = vision_pass_3_verify_calculation(images)
            results["passes"]["pass3_verification"] = pass3

            # =============================================================
            # STEP 5: Compare Pass 2 and Pass 3
            # =============================================================
            print("[Step 5] Comparing calculations...")
            comparison = compare_calculation_passes(pass2, pass3)
            results["passes"]["comparison"] = comparison

            if comparison.get("flag_for_review"):
                results["flag_for_review"] = True
                results["flag_reason"] = comparison.get("reason")
                # Escalation: do NOT guess when mismatched/low confidence
                final_sqft = None
                sqft_source = "calculated_flagged"
                results["passes"]["best_guess"] = pass2.get("total_sqft")

            else:
                final_sqft = comparison.get("final_sqft")
                sqft_source = "calculated_verified"

        # =================================================================
        # STEP 5.5: Compute gross/net sqft (apply exclusions like garage/porch if provided)
        # =================================================================
        chosen_extraction = None
        if sqft_source == "explicit_label":
            chosen_extraction = pass1
        elif sqft_source in ("calculated_verified", "calculated_flagged"):
            chosen_extraction = pass2
        sqft_calc = _compute_final_sqft(chosen_extraction or {})
        results["sqft_calc"] = sqft_calc

        if final_sqft is not None:
            final_sqft = (
                sqft_calc.get("net_sqft") or sqft_calc.get("gross_sqft") or final_sqft
            )

        # =================================================================
        # STEP 6: METADATA EXTRACTION
        # =================================================================
        print("[Step 6] Extracting metadata...")
        metadata_images = [img["data"] for img in pdf_images[:3]]
        project_info = extract_project_metadata(
            metadata_images, email_body, email_from, email_subject
        )
        results["project_info"] = project_info

        project_type = project_info.get("project_type", "RNC")

        # =================================================================
        # STEP 7: COMPLEXITY DETECTION
        # =================================================================
        print("[Step 7] Detecting complexity...")
        complexity = detect_complexity(metadata_images, project_info, email_body)
        results["complexity"] = complexity

        # =================================================================
        # STEP 8: CALCULATE QUOTE
        # =================================================================
        quote = None
        if final_sqft:
            quote = calculate_quote(final_sqft, project_type, complexity)

        # =================================================================
        # BUILD FINAL RESPONSE
        # =================================================================
        
        # Build structures array for frontend (with checkboxes)
        structures_for_ui = []
        if detected_structures:
            for struct in detected_structures:
                structures_for_ui.append({
                    "name": struct.get("name", "Unknown Structure"),
                    "sqft": struct.get("sqft", 0),
                    "is_conditioned": struct.get("is_conditioned", True),
                    "is_primary": struct.get("is_primary", False),
                    "default_selected": struct.get("is_primary", False) or struct.get("is_conditioned", True),
                    "label_text": struct.get("label_text"),
                    "confidence": struct.get("confidence", 0.5)
                })
        
        # Calculate total from primary/conditioned structures
        primary_sqft = sum(s["sqft"] for s in structures_for_ui if s.get("is_primary"))
        if not primary_sqft and structures_for_ui:
            # If no primary marked, use first conditioned structure
            primary_sqft = structures_for_ui[0]["sqft"] if structures_for_ui else final_sqft
        
        results["analysis"] = {
            "client_name": project_info.get("client_name"),
            "project_name": project_info.get("project_name"),
            "project_address": project_info.get("project_address"),
            "city": project_info.get("city"),
            "state": project_info.get("state"),
            "square_footage": final_sqft or primary_sqft,
            "sqft_source": sqft_source,
            "sqft_label_found": (
                pass1.get("label_text") if pass1.get("sqft_found") else None
            ),
            "structures": structures_for_ui,
            "has_multiple_structures": len(structures_for_ui) > 1,
            "project_type": project_type,
            "is_commercial": project_info.get("is_commercial", False),
            "num_stories": project_info.get("num_stories", 1),
            "has_plans": True,
            "complexity_indicators": complexity.get("complexity_indicators", {}),
            "quote": quote,
            "flag_for_review": results["flag_for_review"],
            "flag_reason": results["flag_reason"],
            "missing_info": [],
        }

        # Add warnings
        if not final_sqft:
            results["analysis"]["missing_info"].append(
                "Square footage could not be determined"
            )
            results["flag_for_review"] = True
            results["flag_reason"] = "Could not determine square footage"
            results["analysis"]["flag_for_review"] = True
            results["analysis"]["flag_reason"] = "Could not determine square footage"

        if not project_info.get("project_address"):
            results["analysis"]["missing_info"].append("Project address not found")

        if email_context.get("multiple_structures"):
            results["analysis"]["missing_info"].append(
                "Multiple structures detected - may need additional quote"
            )

        print(
            f"[Complete] SqFt={final_sqft}, Source={sqft_source}, Type={project_type}, Quote=${quote['total'] if quote else 'N/A'}, Flag={results['flag_for_review']}"
        )

    except Exception as e:
        print(f"[Error] {e}")
        import traceback

        traceback.print_exc()
        results["success"] = False
        results["error"] = str(e)
        results["flag_for_review"] = True
        results["flag_reason"] = f"Error during analysis: {str(e)}"

    # Persist audit bundle (best effort)
    try:
        if audit_dir:
            results["audit"]["saved_at"] = datetime.utcnow().isoformat() + "Z"
            _write_json(str(Path(audit_dir) / "results.json"), results)
    except Exception:
        pass

    return results
