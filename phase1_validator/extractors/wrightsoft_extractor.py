"""
ProCalcs Wrightsoft PDF Extractor — Main Extractor
Reads a Wrightsoft Right-Suite Universal PDF and outputs
standardized JSON matching report_schema.json.

This is a plugin in the multi-software architecture.
Other extractors (Elite RHVAC, Cool Calc, etc.) will follow
the same interface but parse different PDF layouts.

ProCalcs HVAC Software — Phase 1 Validator
"""

import json
import re
import fitz  # PyMuPDF

from wrightsoft_helpers import (
    extract_field,
    parse_room_table,
    parse_room_table_continuation,
    parse_ahu_summary,
    parse_equipment_data,
    parse_design_conditions,
    parse_infiltration,
    parse_manual_s_compliance,
)


class WrightsoftExtractor:
    """Extracts structured data from Wrightsoft Right-Suite Universal PDFs."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.pages = self._categorize_pages()

    def _categorize_pages(self) -> dict:
        """
        Scan all pages and categorize by report section.
        Wrightsoft PDFs contain multiple report types in one file:
        - Manual S Compliance Report
        - Building Analysis
        - Load Short Form
        - Construction Data
        - Room Details
        """
        categories = {
            "manual_s": [],
            "building_analysis": [],
            "load_short_form": [],
            "construction": [],
            "room_detail": [],
            "other": [],
        }

        for i, page in enumerate(self.doc):
            text = page.get_text()

            if "Manual S Compliance Report" in text:
                categories["manual_s"].append(i)
            elif "Building Analysis" in text:
                categories["building_analysis"].append(i)
            elif "Load Short Form" in text:
                categories["load_short_form"].append(i)
            elif "Construction" in text and "Wall" in text:
                categories["construction"].append(i)
            else:
                # Check if this is a continuation page for Load Short Form
                # Continuation pages have room data or AHU summaries
                # but no section header
                if re.search(r"AHU\s*-\s*\d+", text) or \
                   re.search(r"ZONE\s+\w+", text):
                    # Check if it has room-like data (uppercase names + numbers)
                    if re.search(r"^[A-Z][A-Z0-9 ]+\n\d+\n", text, re.MULTILINE):
                        categories["load_short_form"].append(i)
                    else:
                        categories["other"].append(i)
                else:
                    categories["other"].append(i)

        return categories

    def extract_all(self) -> dict:
        """
        Main extraction method. Returns complete report data
        matching the standardized schema.
        """
        report = self._empty_report()

        # Step 1: Report metadata
        report["report_metadata"] = self._extract_metadata()

        # Step 2: Project info from first page
        report["project_info"] = self._extract_project_info()

        # Step 3: Design conditions from Building Analysis
        report["design_conditions"] = self._extract_design_conditions()

        # Step 4: Infiltration
        report["infiltration"] = self._extract_infiltration()

        # Step 5: Systems (AHUs) with rooms and equipment
        report["systems"] = self._extract_systems()

        # Step 6: Whole house summary
        report["whole_house_summary"] = self._calculate_summary(
            report["systems"]
        )

        self.doc.close()
        return report

    def _empty_report(self) -> dict:
        """Return empty report structure matching schema."""
        return {
            "report_metadata": {},
            "project_info": {},
            "design_conditions": {},
            "infiltration": {},
            "ventilation": {},
            "systems": [],
            "construction": {},
            "duct_system": {},
            "whole_house_summary": {},
        }

    def _extract_metadata(self) -> dict:
        """Extract software info from first page."""
        text = self.doc[0].get_text()

        version_match = re.search(
            r"Right-Suite.*?Universal\s+(\d{4})\s+([\d.]+)", text
        )
        version = ""
        if version_match:
            version = f"{version_match.group(1)} {version_match.group(2)}"

        date_match = re.search(r"(\d{4}-\w{3}-\d{2})", text)
        report_date = date_match.group(1) if date_match else ""

        # Project name: appears before "Job:" on adjacent line
        lines = text.split("\n")
        project_name = ""
        for i, line in enumerate(lines):
            if line.strip() == "Job:" and i > 0:
                project_name = lines[i - 1].strip()
                break

        acca = "Calculations approved by ACCA" in self.doc[-1].get_text() or \
               any("ACCA" in self.doc[i].get_text() for i in range(len(self.doc)))

        return {
            "source_software": "Wrightsoft Right-Suite Universal",
            "software_version": version,
            "report_date": report_date,
            "project_name": project_name,
            "acca_approved": acca,
            "extraction_confidence": "high",
        }

    def _extract_project_info(self) -> dict:
        """Extract project address and location from first page."""
        text = self.doc[0].get_text()

        info = {
            "client_name": "",
            "project_address": "",
            "city": "",
            "state": "",
            "zip": "",
            "weather_station": "",
            "elevation_ft": 0,
            "latitude": 0.0,
        }

        # "For:" line — client name is on the line BEFORE "For:"
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.strip() == "For:" and i > 0:
                info["client_name"] = lines[i - 1].strip()
                break

        # Address line (after client name typically)
        addr_match = re.search(
            r"(\d+\s+.+?,\s+\w[\w\s]*,\s+[A-Z]{2}\s+\d{5})", text
        )
        if addr_match:
            full_addr = addr_match.group(1).strip()
            info["project_address"] = full_addr
            # Parse city, state, zip
            parts = re.match(
                r"(.+),\s*(.+),\s*([A-Z]{2})\s+(\d{5})", full_addr
            )
            if parts:
                info["city"] = parts.group(2).strip()
                info["state"] = parts.group(3)
                info["zip"] = parts.group(4)

        # Weather station and location from Building Analysis pages
        for pg_idx in self.pages.get("building_analysis", []):
            ba_text = self.doc[pg_idx].get_text()
            ba_lines = ba_text.split("\n")
            ba_lines = [l.strip() for l in ba_lines]

            # Weather station: appears after Location: header
            # Pattern: Location:\n Cooling\n Heating\n Indoor:\n ...\n StationName
            # Station has comma and state code like "Asheville 8 Ssw, NC, US"
            for k, ba_line in enumerate(ba_lines):
                if re.match(r".+,\s*[A-Z]{2},\s*US", ba_line):
                    info["weather_station"] = ba_line
                    break

            # Elevation: value is on line BEFORE "Elevation:"
            for k, ba_line in enumerate(ba_lines):
                if ba_line == "Elevation:" and k > 0:
                    val = re.match(r"\d+", ba_lines[k - 1])
                    if val:
                        info["elevation_ft"] = int(val.group())
                    break

            # Latitude: value is on line BEFORE "Latitude:"
            for k, ba_line in enumerate(ba_lines):
                if ba_line == "Latitude:" and k > 0:
                    val = re.match(r"\d+", ba_lines[k - 1])
                    if val:
                        info["latitude"] = float(val.group())
                    break

            break  # Only need first Building Analysis page

        return info

    def _extract_design_conditions(self) -> dict:
        """Extract from first Load Short Form or Building Analysis page."""
        for pg_idx in self.pages.get("load_short_form", []):
            text = self.doc[pg_idx].get_text()
            return parse_design_conditions(text)

        return {"heating": {}, "cooling": {}}

    def _extract_infiltration(self) -> dict:
        """Extract from first Load Short Form page."""
        for pg_idx in self.pages.get("load_short_form", []):
            text = self.doc[pg_idx].get_text()
            return parse_infiltration(text)

        return {}

    def _extract_systems(self) -> list:
        """
        Extract system (AHU) data including rooms and equipment.
        This is the core extraction — reads Load Short Form pages
        to get room-by-room data, and Manual S pages for equipment.
        """
        systems = []
        last_zone_id = None  # Track current zone for continuation pages

        # Process Load Short Form pages to get room data per AHU
        for pg_idx in self.pages.get("load_short_form", []):
            text = self.doc[pg_idx].get_text()

            # Identify which AHU this page is for
            ahu_match = re.search(r"(AHU\s*-\s*\d+)", text)
            zone_match = re.search(r"(ZONE\s+\w+)", text)

            if ahu_match:
                ahu_id = ahu_match.group(1).strip()

                # Check if this page's header identifies which AHU it belongs to
                # vs an AHU summary line appearing on a continuation page
                is_header_ahu = bool(re.search(
                    rf"Date:.*?\n.*?{re.escape(ahu_id)}", text, re.DOTALL
                )) or bool(re.search(
                    rf"{re.escape(ahu_id)}.*?\n.*?By:", text, re.DOTALL
                ))

                # Is this a new AHU or continuation?
                existing = next(
                    (s for s in systems if s["system_id"] == ahu_id), None
                )

                if existing:
                    # Continuation page — update totals from summary if present
                    summary = parse_ahu_summary(text)
                    if summary and existing["total_area_sqft"] == 0:
                        existing["total_area_sqft"] = summary["total_area_sqft"]
                        existing["heating_load_btuh"] = summary["heating_load_btuh"]
                        existing["cooling_cfm"] = summary["cooling_cfm"]
                        existing["heating_cfm"] = summary["heating_cfm"]

                    # Grab additional rooms — try header parser, then continuation
                    rooms = parse_room_table(text)
                    if not rooms:
                        rooms = parse_room_table_continuation(text)
                    regular_rooms = [r for r in rooms
                                     if not r["room_name"].startswith("ZONE")
                                     and not r["room_name"].startswith("AHU")
                                     and r["room_name"] != "TOTALS"]
                    if regular_rooms and existing["zones"]:
                        for room in regular_rooms:
                            existing["zones"][0]["rooms"].append({
                                "room_name": room["room_name"],
                                "area_sqft": room["area_sqft"],
                                "heating_load_btuh": room["heating_load_btuh"],
                                "cooling_total_btuh": room["cooling_load_btuh"],
                                "heating_cfm": room["heating_cfm"],
                                "cooling_cfm": room["cooling_cfm"],
                            })

                elif not existing:
                    # New AHU
                    system = {
                        "system_id": ahu_id,
                        "system_name": ahu_id,
                        "total_area_sqft": 0,
                        "heating_load_btuh": 0,
                        "cooling_sensible_btuh": 0,
                        "cooling_latent_btuh": 0,
                        "cooling_total_btuh": 0,
                        "cooling_cfm": 0,
                        "heating_cfm": 0,
                        "zones": [],
                        "equipment": {},
                    }

                    # Get AHU summary line
                    summary = parse_ahu_summary(text)
                    if summary:
                        system["total_area_sqft"] = summary["total_area_sqft"]
                        system["heating_load_btuh"] = summary[
                            "heating_load_btuh"
                        ]
                        system["cooling_cfm"] = summary["cooling_cfm"]
                        system["heating_cfm"] = summary["heating_cfm"]

                    # Parse rooms on this page
                    rooms = parse_room_table(text)

                    # Check if rooms include ZONE entries
                    zone_rooms = [r for r in rooms if r["room_name"].startswith("ZONE")]
                    regular_rooms = [r for r in rooms if not r["room_name"].startswith("ZONE")]

                    if zone_rooms:
                        # AHU-2 style: has zones containing rooms
                        for zr in zone_rooms:
                            system["zones"].append({
                                "zone_id": zr["room_name"],
                                "zone_name": zr["room_name"],
                                "total_area_sqft": zr["area_sqft"],
                                "rooms": [],  # Filled from zone detail pages
                            })
                    if regular_rooms:
                        # AHU-1 style: rooms directly under AHU
                        default_zone = {
                            "zone_id": "default",
                            "zone_name": ahu_id,
                            "total_area_sqft": 0,
                            "rooms": [],
                        }
                        for room in regular_rooms:
                            default_zone["rooms"].append({
                                "room_name": room["room_name"],
                                "area_sqft": room["area_sqft"],
                                "heating_load_btuh": room["heating_load_btuh"],
                                "cooling_total_btuh": room["cooling_load_btuh"],
                                "heating_cfm": room["heating_cfm"],
                                "cooling_cfm": room["cooling_cfm"],
                            })
                        default_zone["total_area_sqft"] = sum(
                            r["area_sqft"] for r in default_zone["rooms"]
                        )
                        system["zones"].append(default_zone)

                    systems.append(system)

            elif zone_match and not ahu_match:
                # This is a zone detail page (e.g., ZONE 2A rooms)
                zone_id = zone_match.group(1).strip()
                last_zone_id = zone_id  # Track for continuation pages

                # Try header parser first, fall back to continuation
                rooms = parse_room_table(text)
                if not rooms:
                    rooms = parse_room_table_continuation(text)

                # Filter out zone/AHU summary rows from room list
                real_rooms = [r for r in rooms
                              if not r["room_name"].startswith("ZONE")
                              and not r["room_name"].startswith("AHU")
                              and r["room_name"] != "TOTALS"]

                # Find the parent system that has this zone
                for system in systems:
                    for zone in system["zones"]:
                        if zone["zone_id"] == zone_id:
                            for room in real_rooms:
                                zone["rooms"].append({
                                    "room_name": room["room_name"],
                                    "area_sqft": room["area_sqft"],
                                    "heating_load_btuh": room["heating_load_btuh"],
                                    "cooling_total_btuh": room["cooling_load_btuh"],
                                    "heating_cfm": room["heating_cfm"],
                                    "cooling_cfm": room["cooling_cfm"],
                                })

            elif not ahu_match and not zone_match:
                # Continuation page — no AHU or ZONE in header position
                # Try parsing rooms and assign to last known zone/AHU
                rooms = parse_room_table_continuation(text)
                real_rooms = [r for r in rooms
                              if not r["room_name"].startswith("ZONE")
                              and not r["room_name"].startswith("AHU")
                              and r["room_name"] != "TOTALS"]

                if real_rooms and last_zone_id:
                    for system in systems:
                        for zone in system["zones"]:
                            if zone["zone_id"] == last_zone_id:
                                for room in real_rooms:
                                    zone["rooms"].append({
                                        "room_name": room["room_name"],
                                        "area_sqft": room["area_sqft"],
                                        "heating_load_btuh": room["heating_load_btuh"],
                                        "cooling_total_btuh": room["cooling_load_btuh"],
                                        "heating_cfm": room["heating_cfm"],
                                        "cooling_cfm": room["cooling_cfm"],
                                    })

        # Extract equipment data from Load Short Form pages
        # The LSF equipment section (between "HEATING EQUIPMENT" and "ROOM NAME")
        # has ALL equipment info in a consistent line-by-line format
        for pg_idx in self.pages.get("load_short_form", []):
            text = self.doc[pg_idx].get_text()
            ahu_match = re.search(r"(AHU\s*-\s*\d+)", text)
            if not ahu_match:
                continue
            ahu_id = ahu_match.group(1).strip()

            # Only process header pages (not continuations)
            if not re.search(r"HEATING EQUIPMENT", text):
                continue

            for system in systems:
                if system["system_id"] != ahu_id:
                    continue

                lines = [l.strip() for l in text.split("\n")]
                equip = {
                    "manufacturer": "",
                    "outdoor_model": "",
                    "indoor_model": "",
                    "ahri_ref": "",
                    "type": "Split ASHP",
                    "hspf2": 0.0,
                    "seer2": 0.0,
                    "eer2": 0.0,
                    "nominal_tons": 0.0,
                    "heating_input_btuh": 0,
                    "heating_output_btuh": 0,
                    "sensible_cooling_btuh": 0,
                    "latent_cooling_btuh": 0,
                    "total_cooling_btuh": 0,
                    "heating_airflow_cfm": 0,
                    "cooling_airflow_cfm": 0,
                    "heating_static_pressure": 0.0,
                    "cooling_static_pressure": 0.0,
                    "temperature_rise_f": 0,
                    "load_sensible_heat_ratio": 0.0,
                    "capacity_balance_point_f": 0,
                    "backup_model": "",
                    "backup_kw": 0.0,
                    "backup_btuh": 0,
                    "backup_afue": 0,
                }

                # Walk lines sequentially — the format alternates
                # heating label, cooling label on the same "row"
                for k, line in enumerate(lines):
                    nl = lines[k + 1] if k + 1 < len(lines) else ""

                    # Manufacturer (first "Make" is heating side)
                    if line == "Make" and nl and nl != "Make":
                        if not equip["manufacturer"]:
                            equip["manufacturer"] = nl

                    # Trade name
                    elif line == "Trade" and nl and nl != "Trade":
                        if not equip.get("trade"):
                            equip["trade"] = nl

                    # Model (heating side) / Condenser (cooling outdoor)
                    elif line == "Model" and nl:
                        equip["outdoor_model"] = nl
                    elif line == "Cond" and nl:
                        equip["outdoor_model"] = nl
                    elif line == "Coil" and nl:
                        equip["indoor_model"] = nl

                    # AHRI ref
                    elif line == "AHRI ref" and re.match(r"\d+", nl):
                        if not equip["ahri_ref"]:
                            equip["ahri_ref"] = nl

                    # Efficiency ratings
                    elif "HSPF2" in line:
                        m = re.search(r"([\d.]+)\s*HSPF2", line)
                        if m:
                            equip["hspf2"] = float(m.group(1))
                    elif "SEER2" in line:
                        m = re.search(r"([\d.]+)\s*SEER2", line)
                        if m:
                            equip["seer2"] = float(m.group(1))
                        m2 = re.search(r"([\d.]+)\s*EER2", line)
                        if m2:
                            equip["eer2"] = float(m2.group(1))

                    # Heating input (line before "Heating output")
                    elif line == "Heating input":
                        # Next meaningful number after "Btuh"
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["heating_input_btuh"] = int(lines[n])
                                break

                    # Heating output
                    elif line == "Heating output":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["heating_output_btuh"] = int(lines[n])
                                break

                    # Sensible cooling
                    elif line == "Sensible cooling":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["sensible_cooling_btuh"] = int(lines[n])
                                break

                    # Latent cooling
                    elif line == "Latent cooling":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["latent_cooling_btuh"] = int(lines[n])
                                break

                    # Total cooling
                    elif line == "Total cooling":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["total_cooling_btuh"] = int(lines[n])
                                break

                    # Temperature rise
                    elif line == "Temperature rise":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            if re.match(r"^\d+$", lines[n]):
                                equip["temperature_rise_f"] = int(lines[n])
                                break

                    # Static pressure (first is heating, second is cooling)
                    elif line == "Static pressure":
                        for n in range(k + 1, min(k + 4, len(lines))):
                            m = re.match(r"^[\d.]+$", lines[n])
                            if m:
                                if equip["heating_static_pressure"] == 0:
                                    equip["heating_static_pressure"] = float(lines[n])
                                else:
                                    equip["cooling_static_pressure"] = float(lines[n])
                                break

                    # Load SHR
                    elif line == "Load sensible heat ratio":
                        if nl and re.match(r"^[\d.]+$", nl):
                            equip["load_sensible_heat_ratio"] = float(nl)

                    # Balance point
                    elif "Capacity balance point" in line:
                        m = re.search(r"=\s*([-\d]+)", line)
                        if m:
                            equip["capacity_balance_point_f"] = int(m.group(1))

                    # Backup equipment
                    elif line.startswith("Backup:"):
                        equip["backup_model"] = line.replace("Backup:", "").strip()
                    elif line.startswith("Input ="):
                        m = re.search(r"Input = ([\d.]+) kW.*Output = (\d+) Btuh.*?(\d+) AFUE", line)
                        if m:
                            equip["backup_kw"] = float(m.group(1))
                            equip["backup_btuh"] = int(m.group(2))
                            equip["backup_afue"] = int(m.group(3))

                # Calculate nominal tons from total cooling
                if equip["total_cooling_btuh"] > 0:
                    equip["nominal_tons"] = round(
                        equip["total_cooling_btuh"] / 12000, 1
                    )

                system["equipment"] = equip
                break

        # Add Manual S compliance data (capacities and percentages)
        # AND equipment identification from Manual S pages
        for pg_idx in self.pages.get("manual_s", []):
            text = self.doc[pg_idx].get_text()

            # Which AHU is this Manual S for?
            ahu_match = re.search(r"(AHU\s*-\s*\d+)", text)
            if ahu_match:
                ahu_id = ahu_match.group(1).strip()
                for system in systems:
                    if system["system_id"] == ahu_id:
                        # Get equipment ID from Manual S if not already set
                        if not system["equipment"].get("type"):
                            equip_data = parse_equipment_data(text)
                            for key, val in equip_data.items():
                                if val and not system["equipment"].get(key):
                                    system["equipment"][key] = val

                        ms_data = parse_manual_s_compliance(text)
                        system["equipment"].update(ms_data)

                        # Get sensible/latent from Manual S page
                        sens_match = re.search(
                            r"(\d+)\s*\n\s*Sensible gain", text
                        )
                        if sens_match:
                            system["cooling_sensible_btuh"] = int(
                                sens_match.group(1)
                            )
                        lat_match = re.search(
                            r"(\d+)\s*\n\s*Latent gain", text
                        )
                        if lat_match:
                            system["cooling_latent_btuh"] = int(
                                lat_match.group(1)
                            )
                        total_match = re.search(
                            r"(\d+)\s*\n\s*Total gain", text
                        )
                        if total_match:
                            system["cooling_total_btuh"] = int(
                                total_match.group(1)
                            )
                        break

        return systems

    def _calculate_summary(self, systems: list) -> dict:
        """Calculate whole-house summary from system data."""
        total_area = sum(s.get("total_area_sqft", 0) for s in systems)
        total_htg = sum(s.get("heating_load_btuh", 0) for s in systems)
        total_clg_sens = sum(
            s.get("cooling_sensible_btuh", 0) for s in systems
        )
        total_clg_lat = sum(
            s.get("cooling_latent_btuh", 0) for s in systems
        )
        total_clg = sum(s.get("cooling_total_btuh", 0) for s in systems)
        total_rooms = sum(
            len(r)
            for s in systems
            for z in s.get("zones", [])
            for r in [z.get("rooms", [])]
        )

        return {
            "total_conditioned_area_sqft": total_area,
            "total_heating_load_btuh": total_htg,
            "total_cooling_sensible_btuh": total_clg_sens,
            "total_cooling_latent_btuh": total_clg_lat,
            "total_cooling_total_btuh": total_clg,
            "number_of_systems": len(systems),
            "number_of_rooms": total_rooms,
            "sensible_heat_ratio": (
                round(total_clg_sens / total_clg, 2)
                if total_clg > 0
                else 0.0
            ),
        }


# === COMMAND LINE INTERFACE ===

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python wrightsoft_extractor.py <pdf_path> [output.json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    extractor = WrightsoftExtractor(pdf_path)
    report = extractor.extract_all()

    output_json = json.dumps(report, indent=2)

    if output_path:
        with open(output_path, "w") as f:
            f.write(output_json)
        print(f"Extracted to: {output_path}")
    else:
        print(output_json)
