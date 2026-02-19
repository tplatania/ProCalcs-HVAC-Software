"""
ProCalcs Wrightsoft PDF Extractor — Parsing Helpers
Low-level text parsing functions for Wrightsoft Right-Suite Universal PDFs.
These handle the messy text extraction patterns.

ProCalcs HVAC Software — Phase 1 Validator
"""

import re


def extract_field(text: str, label: str, value_type: str = "str") -> any:
    """
    Extract a value that appears after a label in Wrightsoft's text format.
    Wrightsoft PDFs extract with labels and values on separate lines or
    in label:value patterns.

    value_type: 'str', 'int', 'float'
    """
    # Pattern 1: "Label\nValue" (common in Wrightsoft)
    pattern1 = re.compile(
        rf"{re.escape(label)}\s*\n\s*(.+?)(?:\n|$)", re.IGNORECASE
    )
    match = pattern1.search(text)

    if not match:
        # Pattern 2: "Label: Value" or "Label  Value"
        pattern2 = re.compile(
            rf"{re.escape(label)}[:\s]+(.+?)(?:\n|$)", re.IGNORECASE
        )
        match = pattern2.search(text)

    if not match:
        return None

    raw = match.group(1).strip()

    if value_type == "int":
        # Extract first number
        num = re.search(r"[-\d,]+", raw)
        return int(num.group().replace(",", "")) if num else 0
    elif value_type == "float":
        num = re.search(r"[-\d,.]+", raw)
        return float(num.group().replace(",", "")) if num else 0.0
    return raw


def extract_paired_field(text: str, label: str) -> str:
    """
    Wrightsoft often puts the value BEFORE the label on the same line.
    Example: 'Btuh\n35311\nSensible gain:'
    Or value and label on adjacent lines.
    """
    # Try: value appears on line before the label
    pattern = re.compile(
        rf"(\S+)\s*\n\s*{re.escape(label)}", re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        return match.group(1).strip()

    # Try: label then value on next line
    pattern2 = re.compile(
        rf"{re.escape(label)}\s*\n\s*(\S+)", re.IGNORECASE
    )
    match = pattern2.search(text)
    if match:
        return match.group(1).strip()

    return None


def parse_room_table(text: str) -> list:
    """
    Parse the room data table from a Load Short Form page.
    Wrightsoft extracts with each field on a SEPARATE LINE:
    ROOM NAME
    Area
    Htg load
    ...
    BREAKFAST
    267
    4784
    3563
    225
    173

    Returns list of dicts with room data.
    """
    rooms = []

    # Find the room table section - starts after the header row
    header_match = re.search(
        r"ROOM NAME\s+Area\s+Htg load\s+Clg load\s+Htg AVF\s+Clg AVF",
        text, re.IGNORECASE
    )
    if not header_match:
        return rooms

    # Get text after header
    after_header = text[header_match.end():]

    # Skip the units row "(ft²) (Btuh) (Btuh) (cfm) (cfm)"
    units_match = re.search(r"\(cfm\)\s*\n", after_header)
    if units_match:
        after_header = after_header[units_match.end():]

    # Wrightsoft puts each value on a SEPARATE line:
    # ROOM_NAME\n area\n htg_load\n clg_load\n htg_cfm\n clg_cfm\n
    lines = after_header.strip().split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Room/zone/AHU names are uppercase text (may contain spaces/digits)
        # Can start with digits like "2F HALL"
        # Skip if it's a pure number or a known non-room keyword
        if re.match(r"^[A-Z0-9][A-Z0-9 ]+$", line) and not line.startswith("Other") and not re.match(r"^\d+$", line):
            name = line

            # Read next 5 values (area, htg_load, clg_load, htg_cfm, clg_cfm)
            values = []
            j = i + 1
            while j < len(lines) and len(values) < 5:
                val = lines[j].strip()
                if re.match(r"^-?\d+$", val):
                    values.append(int(val))
                    j += 1
                else:
                    break

            if len(values) == 5:
                # Skip summary rows
                if name == "TOTALS":
                    i = j
                    continue

                rooms.append({
                    "room_name": name,
                    "area_sqft": values[0],
                    "heating_load_btuh": values[1],
                    "cooling_load_btuh": values[2],
                    "heating_cfm": values[3],
                    "cooling_cfm": values[4],
                })
                i = j
                continue

        i += 1

    return rooms


def parse_room_table_continuation(text: str) -> list:
    """
    Parse rooms from a continuation page that has NO 'ROOM NAME' header.
    These pages start with room data right after the Wrightsoft boilerplate.
    Uses the same name + 5 numbers pattern but starts from the top.
    """
    rooms = []

    lines = text.strip().split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    # Skip known boilerplate lines at top of page
    start = 0
    for k, line in enumerate(lines):
        if line.startswith("Calculations approved") or \
           line.startswith("2025-") or line.startswith("2026-") or \
           line.startswith("Right-Suite") or \
           line.startswith("Page ") or line.startswith("..."):
            continue
        start = k
        break

    i = start
    while i < len(lines):
        line = lines[i]

        if re.match(r"^[A-Z0-9][A-Z0-9 ]+$", line) and \
           not line.startswith("Other") and \
           not line.startswith("Equip") and \
           not line.startswith("RSM") and \
           not line.startswith("Latent") and \
           not re.match(r"^\d+$", line):
            name = line

            values = []
            j = i + 1
            while j < len(lines) and len(values) < 5:
                val = lines[j].strip()
                if re.match(r"^-?\d+$", val):
                    values.append(int(val))
                    j += 1
                else:
                    break

            if len(values) == 5:
                if name == "TOTALS":
                    i = j
                    continue

                rooms.append({
                    "room_name": name,
                    "area_sqft": values[0],
                    "heating_load_btuh": values[1],
                    "cooling_load_btuh": values[2],
                    "heating_cfm": values[3],
                    "cooling_cfm": values[4],
                })
                i = j
                continue

        i += 1

    return rooms


def parse_ahu_summary(text: str) -> dict:
    """
    Parse the AHU summary line from Load Short Form.
    Wrightsoft puts each value on separate lines:
    AHU - 1
    2682
    35662
    34639
    1678
    1678
    """
    lines = text.strip().split("\n")
    lines = [l.strip() for l in lines]

    for i, line in enumerate(lines):
        if re.match(r"AHU\s*-\s*\d+", line):
            # Read next 5 numeric values
            values = []
            j = i + 1
            while j < len(lines) and len(values) < 5:
                val = lines[j].strip()
                if re.match(r"^-?\d+$", val):
                    values.append(int(val))
                    j += 1
                else:
                    break

            if len(values) >= 5:
                return {
                    "system_id": line.strip(),
                    "total_area_sqft": values[0],
                    "heating_load_btuh": values[1],
                    "cooling_load_btuh": values[2],
                    "heating_cfm": values[3],
                    "cooling_cfm": values[4],
                }

    return None


def parse_equipment_data(text: str) -> dict:
    """
    Parse equipment info from Manual S Compliance or Load Short Form page.
    Wrightsoft format has label on one line, value on the NEXT line.
    But some fields are reversed (value before label).
    """
    equip = {
        "manufacturer": "",
        "outdoor_model": "",
        "indoor_model": "",
        "ahri_ref": "",
        "type": "",
        "hspf2": 0.0,
        "seer2": 0.0,
        "eer2": 0.0,
    }

    lines = text.split("\n")
    lines = [l.strip() for l in lines]

    for i, line in enumerate(lines):
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

        # Equipment type: value is on line BEFORE "Equipment type:"
        if line == "Equipment type:" and i > 0:
            equip["type"] = lines[i - 1].strip()

        # Manufacturer: "Make" then value on next line (Load Short Form)
        elif line == "Make" and next_line and not next_line.startswith("Make"):
            if not equip["manufacturer"]:
                equip["manufacturer"] = next_line

        # Model/Cond/Coil from Load Short Form
        elif line == "Model" and next_line:
            if not equip["outdoor_model"]:
                equip["outdoor_model"] = next_line
        elif line == "Cond" and next_line:
            equip["outdoor_model"] = next_line  # Cond is outdoor unit
        elif line == "Coil" and next_line:
            equip["indoor_model"] = next_line

        # AHRI ref
        elif line == "AHRI ref" and next_line and re.match(r"\d+", next_line):
            if not equip["ahri_ref"]:
                equip["ahri_ref"] = next_line

    # Efficiency ratings (can appear anywhere in text)
    hspf_match = re.search(r"([\d.]+)\s*HSPF2", text)
    if hspf_match:
        equip["hspf2"] = float(hspf_match.group(1))

    seer_match = re.search(r"([\d.]+)\s*SEER2", text)
    if seer_match:
        equip["seer2"] = float(seer_match.group(1))

    eer_match = re.search(r"([\d.]+)\s*EER2", text)
    if eer_match:
        equip["eer2"] = float(eer_match.group(1))

    return equip


def parse_design_conditions(text: str) -> dict:
    """
    Parse design conditions from Building Analysis or Load Short Form.
    """
    conditions = {
        "heating": {
            "outdoor_temp_f": 0,
            "indoor_temp_f": 70,
            "temperature_difference_f": 0,
        },
        "cooling": {
            "outdoor_temp_f": 0,
            "indoor_temp_f": 75,
            "temperature_difference_f": 0,
            "daily_range": "",
            "grains_difference": 0,
        },
    }

    # From Load Short Form: "84  17  Outside db (°F)"
    # Cooling is first number, heating is second
    outside_match = re.search(r"(\d+)\s+(\d+)\s+Outside db", text)
    if outside_match:
        conditions["cooling"]["outdoor_temp_f"] = int(outside_match.group(1))
        conditions["heating"]["outdoor_temp_f"] = int(outside_match.group(2))

    inside_match = re.search(r"(\d+)\s+(\d+)\s+Inside db", text)
    if inside_match:
        conditions["cooling"]["indoor_temp_f"] = int(inside_match.group(1))
        conditions["heating"]["indoor_temp_f"] = int(inside_match.group(2))

    td_match = re.search(r"(\d+)\s+(\d+)\s+Design TD", text)
    if td_match:
        conditions["cooling"]["temperature_difference_f"] = int(
            td_match.group(1)
        )
        conditions["heating"]["temperature_difference_f"] = int(
            td_match.group(2)
        )

    # Daily range
    range_match = re.search(r"(\w+)\s*\n\s*-\s*\n\s*Daily range", text)
    if range_match:
        conditions["cooling"]["daily_range"] = range_match.group(1).strip()

    # Moisture difference
    moist_match = re.search(
        r"([\d.]+)\s+([\d.]+)\s+Moisture difference", text
    )
    if moist_match:
        conditions["cooling"]["grains_difference"] = float(
            moist_match.group(1)
        )

    return conditions


def parse_infiltration(text: str) -> dict:
    """
    Parse infiltration data from Load Short Form or Building Analysis.
    """
    infil = {
        "method": "",
        "tightness_category": "",
        "ach_at_50pa": 0.0,
        "cfm_at_50pa": 0,
        "blower_door_tested": False,
    }

    # Method
    method_match = re.search(r"(Blower door|Estimate)\s*\n\s*Method", text, re.IGNORECASE)
    if method_match:
        infil["method"] = method_match.group(1).strip()
        infil["blower_door_tested"] = "blower" in infil["method"].lower()

    # Pressure / ACH / AVF: "50 Pa / 3.0 / 3669 cfm"
    pach_match = re.search(
        r"(\d+)\s*Pa\s*/\s*([\d.]+)\s*/\s*(\d+)\s*cfm", text
    )
    if pach_match:
        infil["ach_at_50pa"] = float(pach_match.group(2))
        infil["cfm_at_50pa"] = int(pach_match.group(3))

    return infil


def parse_manual_s_compliance(text: str) -> dict:
    """
    Parse Manual S compliance data from the Manual S page.
    Wrightsoft format: value on line BEFORE the label.
    Example:
      % of load
      108
      Btuh
      38192
      Sensible capacity:
    """
    ms = {
        "heating_capacity_btuh": 0,
        "cooling_sensible_btuh": 0,
        "cooling_latent_btuh": 0,
        "cooling_total_btuh": 0,
        "heating_percentage": 0,
        "cooling_sensible_percentage": 0,
        "cooling_total_percentage": 0,
        "sensible_heat_ratio": 0,
    }

    lines = text.split("\n")
    lines = [l.strip() for l in lines]

    # Find "Cooling Equipment" and "Heating Equipment" sections
    cooling_start = None
    heating_start = None
    for i, line in enumerate(lines):
        if line == "Cooling Equipment":
            cooling_start = i
        elif line == "Heating Equipment":
            heating_start = i

    # Parse cooling section for sensible/total capacity and percentages
    if cooling_start is not None:
        section_end = heating_start if heating_start and heating_start > cooling_start else len(lines)
        cooling_lines = lines[cooling_start:section_end]

        for i, line in enumerate(cooling_lines):
            if "Sensible capacity" in line and i >= 2:
                # Two lines back: Btuh value, three back: % value
                for j in range(i - 1, max(i - 5, 0), -1):
                    if re.match(r"^\d+$", cooling_lines[j]):
                        ms["cooling_sensible_btuh"] = int(cooling_lines[j])
                        break
                for j in range(i - 1, max(i - 5, 0), -1):
                    if "% of load" in cooling_lines[j] and j + 1 < len(cooling_lines):
                        val = re.match(r"^\d+$", cooling_lines[j + 1])
                        if val:
                            ms["cooling_sensible_percentage"] = int(val.group())
                        break

            elif "Total capacity" in line and "Sensible" not in line and i >= 2:
                for j in range(i - 1, max(i - 5, 0), -1):
                    if re.match(r"^\d+$", cooling_lines[j]):
                        ms["cooling_total_btuh"] = int(cooling_lines[j])
                        break
                for j in range(i - 1, max(i - 5, 0), -1):
                    if "% of load" in cooling_lines[j] and j + 1 < len(cooling_lines):
                        val = re.match(r"^\d+$", cooling_lines[j + 1])
                        if val:
                            ms["cooling_total_percentage"] = int(val.group())
                        break

    # Parse heating section for output capacity and percentage
    if heating_start is not None:
        heating_lines = lines[heating_start:]

        for i, line in enumerate(heating_lines):
            if "Output capacity" in line and i >= 2:
                for j in range(i - 1, max(i - 5, 0), -1):
                    if re.match(r"^\d+$", heating_lines[j]):
                        ms["heating_capacity_btuh"] = int(heating_lines[j])
                        break
                for j in range(i - 1, max(i - 5, 0), -1):
                    if "% of load" in heating_lines[j] and j + 1 < len(heating_lines):
                        val = re.match(r"^\d+$", heating_lines[j + 1])
                        if val:
                            ms["heating_percentage"] = int(val.group())
                        break

    # SHR
    shr_match = re.search(r"SHR:\s*\n\s*%\s*\n\s*(\d+)", text)
    if shr_match:
        ms["sensible_heat_ratio"] = int(shr_match.group(1))

    return ms
