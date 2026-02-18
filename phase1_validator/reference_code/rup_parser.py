"""
RUP File Parser for Wrightsoft Right-Suite Universal files
Extracts project data for QC validation
"""

import re
from typing import Dict, List, Any


def clean_string(s: str) -> str:
    """Remove non-printable characters and clean up string."""
    # Keep only printable ASCII and common chars
    cleaned = ''.join(c if (c.isprintable() and ord(c) < 128) else '' for c in s)
    return ' '.join(cleaned.split()).strip()


def parse_rup_file(file_bytes: bytes) -> Dict[str, Any]:
    """
    Parse a .rup file and extract structured project data.
    
    Args:
        file_bytes: Raw bytes from .rup file
        
    Returns:
        Dictionary with extracted project data
    """
    # Decode as UTF-16-LE (Wrightsoft's encoding)
    try:
        text = file_bytes.decode('utf-16-le', errors='replace')
    except Exception:
        text = file_bytes.decode('utf-8', errors='replace')
    
    result = {
        'header': {},
        'project': {},
        'location': {},
        'rooms': [],
        'equipment': {},
        'construction': {},
        'raw_sections': []
    }
    
    # 1. Parse header
    header = text[:1000]
    
    if 'APP=' in header:
        app_match = re.search(r'APP=([^\r\n\x00]+)', header)
        if app_match:
            result['header']['application'] = app_match.group(1).strip()
    
    if 'VRSN=' in header:
        ver_match = re.search(r'VRSN=([^\r\n\x00]+)', header)
        if ver_match:
            result['header']['version'] = ver_match.group(1).strip()
    
    if 'TIMESTAMP=' in header:
        ts_match = re.search(r'TIMESTAMP=([^\r\n\x00]+)', header)
        if ts_match:
            result['header']['timestamp'] = ts_match.group(1).strip()
    
    # 2. Parse project info (address, client, etc.)
    # Look for address pattern: number + street + city + state + zip
    addr_match = re.search(
        r'(\d{2,5}\s+[A-Za-z][A-Za-z\s]{3,40}(?:Road|Rd|Street|St|Ave|Avenue|Drive|Dr|Lane|Ln|Way|Court|Ct|Circle|Blvd|Boulevard|Place|Pl)[^\x00]{0,50}(?:FL|CA|TX|NY|GA|NC|SC|AZ|NV|CO|WA|OR|OH|PA|IL|MI|VA|TN|AL|LA|MS|AR|KY|MO|OK|KS|NE|IA|IN|WI|MN|MD|NJ|CT|MA|NH|VT|ME|RI|DE|WV|MT|ID|WY|ND|SD|NM|UT|HI|AK)[^\x00]{0,30}\d{5})',
        text, re.IGNORECASE
    )
    if addr_match:
        addr_raw = addr_match.group(1)
        addr_clean = ''.join(c if c.isprintable() else ' ' for c in addr_raw)
        result['project']['address'] = ' '.join(addr_clean.split())
    
    # Look for client name (near address)
    client_match = re.search(r'(?:Client|Owner|Customer|Name)[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)', text)
    if client_match:
        result['project']['client'] = client_match.group(1)
    
    # 3. Parse weather/location data
    if 'WTHRDATA' in text:
        wth_start = text.find('BEG=WTHRDATA')
        wth_end = text.find('END=WTHRDATA')
        if wth_start > 0 and wth_end > wth_start:
            wth_section = text[wth_start:wth_end]
            
            # Look for weather station name
            station_match = re.search(r'([A-Za-z\s]+(?:Executive|International|Regional|Municipal|Airport)[^|]{0,30})', wth_section)
            if station_match:
                station = ''.join(c if c.isprintable() else '' for c in station_match.group(1))
                result['location']['weather_station'] = station.strip()
            
            # Look for state
            state_match = re.search(r'\|([A-Z]{2})\|', wth_section)
            if state_match:
                result['location']['state'] = state_match.group(1)
    
    # 4. Parse rooms - improved extraction
    room_pattern = r'((?:MASTER|PRIMARY|BEDROOM|LIVING|FAMILY|KITCHEN|DINING|GARAGE|BATH|LAUNDRY|OFFICE|GREAT|FOYER|ENTRY|CLOSET|PANTRY|UTILITY|HALL|BONUS|STUDY|DEN|NOOK|BREAKFAST|PORCH|PATIO|STORAGE|MECHANICAL|MUD|POWDER)(?:\s*(?:ROOM|RM|BATH|\d+)?)?)'
    room_matches = re.findall(room_pattern, text, re.IGNORECASE)
    
    unique_rooms = []
    seen = set()
    for r in room_matches:
        cleaned = clean_string(r).upper()
        # Skip if it's a file path or contains unwanted patterns
        if any(x in cleaned for x in ['.CAT', '.RUP', '.PDF', 'APPLIANCES', 'EXAMINER', 'SCENARIO']):
            continue
        if len(cleaned) > 2 and len(cleaned) < 30 and cleaned not in seen:
            seen.add(cleaned)
            unique_rooms.append(cleaned)
    
    result['rooms'] = unique_rooms[:30]  # Limit to 30 rooms
    
    # 5. Parse equipment
    # Look for model numbers
    model_pattern = r'([A-Z]{2,4}[0-9]{2,6}[A-Z0-9\-]{2,20})'
    models = re.findall(model_pattern, text)
    unique_models = list(dict.fromkeys(m for m in models if len(m) > 8))
    result['equipment']['model_numbers'] = unique_models[:10]
    
    # Look for tonnage/capacity
    tonnage_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:ton|TON)', text)
    if tonnage_match:
        result['equipment']['tonnage'] = tonnage_match.group(1)
    
    # Look for SEER
    seer_match = re.search(r'SEER\s*[=:]?\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if seer_match:
        result['equipment']['seer'] = seer_match.group(1)
    
    # Look for CFM values
    cfm_matches = re.findall(r'(\d{2,5})\s*CFM', text, re.IGNORECASE)
    if cfm_matches:
        result['equipment']['cfm_values'] = list(set(cfm_matches))[:10]
    
    # 6. Parse construction values
    # Look for R-values
    r_values = re.findall(r'R[-\s]?(\d{1,2}(?:\.\d)?)', text)
    if r_values:
        result['construction']['r_values'] = list(set(r_values))
    
    # Look for U-factor
    u_matches = re.findall(r'U[-\s]?(?:factor|value)?[=:\s]*(\d?\.\d{2,3})', text, re.IGNORECASE)
    if u_matches:
        result['construction']['u_factors'] = list(set(u_matches))
    
    # 7. List section markers found
    sections = re.findall(r'BEG=([A-Z0-9]+)', text)
    result['raw_sections'] = list(dict.fromkeys(sections))[:50]
    
    return result


def format_rup_for_ai(parsed_data: Dict[str, Any]) -> str:
    """
    Format parsed RUP data into readable text for AI validation.
    
    Args:
        parsed_data: Output from parse_rup_file()
        
    Returns:
        Formatted string for AI analysis
    """
    lines = []
    
    lines.append("=== WRIGHTSOFT PROJECT FILE ===")
    lines.append("")
    
    # Header
    if parsed_data.get('header'):
        h = parsed_data['header']
        if h.get('application'):
            lines.append(f"Software: {h['application']}")
        if h.get('version'):
            lines.append(f"Version: {h['version']}")
        if h.get('timestamp'):
            lines.append(f"Last Saved: {h['timestamp']}")
        lines.append("")
    
    # Project info
    if parsed_data.get('project'):
        p = parsed_data['project']
        lines.append("=== PROJECT INFO ===")
        if p.get('address'):
            lines.append(f"Address: {p['address']}")
        if p.get('client'):
            lines.append(f"Client: {p['client']}")
        lines.append("")
    
    # Location
    if parsed_data.get('location'):
        loc = parsed_data['location']
        lines.append("=== LOCATION/WEATHER ===")
        if loc.get('weather_station'):
            lines.append(f"Weather Station: {loc['weather_station']}")
        if loc.get('state'):
            lines.append(f"State: {loc['state']}")
        lines.append("")
    
    # Rooms
    if parsed_data.get('rooms'):
        lines.append("=== ROOMS ===")
        for room in parsed_data['rooms']:
            lines.append(f"  - {room}")
        lines.append(f"Total: {len(parsed_data['rooms'])} rooms")
        lines.append("")
    
    # Equipment
    if parsed_data.get('equipment'):
        eq = parsed_data['equipment']
        lines.append("=== EQUIPMENT ===")
        if eq.get('tonnage'):
            lines.append(f"Tonnage: {eq['tonnage']} tons")
        if eq.get('seer'):
            lines.append(f"SEER: {eq['seer']}")
        if eq.get('cfm_values'):
            lines.append(f"CFM Values: {', '.join(eq['cfm_values'])}")
        if eq.get('model_numbers'):
            for model in eq['model_numbers'][:5]:
                lines.append(f"  Model: {model}")
        lines.append("")
    
    # Construction
    if parsed_data.get('construction'):
        con = parsed_data['construction']
        lines.append("=== CONSTRUCTION VALUES ===")
        if con.get('r_values'):
            lines.append(f"R-Values found: {', '.join(con['r_values'])}")
        if con.get('u_factors'):
            lines.append(f"U-Factors found: {', '.join(con['u_factors'])}")
        lines.append("")
    
    # Sections present
    if parsed_data.get('raw_sections'):
        lines.append("=== DATA SECTIONS PRESENT ===")
        lines.append(", ".join(parsed_data['raw_sections'][:20]))
    
    return "\n".join(lines)


# Test function
if __name__ == "__main__":
    import sys
    
    test_file = r"G:\My Drive\Claude Projects\ProCalcs_Design_Process\Test_Project\1901 Loch Berry\1901 Loch Berry\Working Drawings\1901 Loch Berry Residence Load Calcs.rup"
    
    with open(test_file, 'rb') as f:
        raw = f.read()
    
    parsed = parse_rup_file(raw)
    formatted = format_rup_for_ai(parsed)
    
    print(formatted)
