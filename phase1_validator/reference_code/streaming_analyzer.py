"""
ProCalcs Streaming Project Analyzer
Processes files one-by-one with real-time progress updates
"""

import json
import io
import PyPDF2
import anthropic
from flask import Response, stream_with_context

try:
    from .config import Config
    from . import zoho_integration as zoho
except ImportError:
    from config import Config
    import zoho_integration as zoho


def analyze_single_file(token, file_info, folder_key):
    """Download and extract text from a single file"""
    fname = file_info.get('attributes', {}).get('name', 'Unknown')
    file_id = file_info.get('id')
    
    downloadable_extensions = ['.pdf', '.txt', '.msg', '.eml']
    
    if not any(fname.lower().endswith(e) for e in downloadable_extensions):
        return None
    
    try:
        content = zoho.download_file_content(token, file_id)
        if not content:
            return None
        
        text = ""
        
        if fname.lower().endswith('.pdf'):
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                
                # Extract form fields first
                fields = pdf_reader.get_fields()
                if fields:
                    text += "=== FORM FIELD VALUES ===\n"
                    for field_name, field_data in fields.items():
                        value = field_data.get('/V', '')
                        if isinstance(value, str) and value and value not in ['', '/Off']:
                            text += f"{field_name}: {value}\n"
                        elif hasattr(value, 'get_object'):
                            try:
                                resolved = str(value.get_object())
                                if resolved and resolved not in ['', '/Off']:
                                    text += f"{field_name}: {resolved}\n"
                            except:
                                pass
                    text += "=== END FORM FIELDS ===\n\n"
                
                # Extract page text
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            except Exception as e:
                print(f"[STREAM] PDF extraction failed for {fname}: {e}")
                return None
                
        elif fname.lower().endswith(('.txt', '.msg', '.eml')):
            try:
                text = content.decode('utf-8', errors='ignore')
            except:
                text = str(content)
        
        if text:
            return {
                'filename': fname,
                'folder': folder_key,
                'text': text[:15000]
            }
        return None
        
    except Exception as e:
        print(f"[STREAM] Error processing {fname}: {e}")
        return None


def analyze_file_with_ai(client, file_data, project_name, client_name):
    """Use AI to analyze a single file and extract key information"""
    
    prompt = f"""Analyze this HVAC project document and extract key information.

PROJECT: {project_name}
CLIENT: {client_name}
FILE: {file_data['filename']} (from {file_data['folder']})

CONTENT:
{file_data['text'][:10000]}

Extract any of these details if present:
- Address/Location
- Contact phone number
- Contact email
- Project type (RNC/RREN/CNC/CREN)
- Square footage
- Number of systems
- Equipment type (Heat Pump, Mini-Split, Furnace, etc.)
- Brand, SEER rating
- Construction details (wall types, insulation, R-values)
- Any special notes or requirements

Return a JSON object with found information. Use "N/A" for fields not found in this file.
Return ONLY valid JSON, no markdown."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        ai_response = response.content[0].text.strip()
        
        # Parse JSON
        import re
        if ai_response.startswith('```'):
            ai_response = ai_response.split('```')[1]
            if ai_response.startswith('json'):
                ai_response = ai_response[4:]
        
        json_match = re.search(r'\{[\s\S]*\}', ai_response)
        if json_match:
            return json.loads(json_match.group())
        return {}
        
    except Exception as e:
        print(f"[STREAM] AI analysis failed for {file_data['filename']}: {e}")
        return {}


def combine_file_analyses(client, file_analyses, project_name, client_name):
    """Combine individual file analyses into final project summary"""
    
    combined_data = json.dumps(file_analyses, indent=2)
    
    prompt = f"""You analyzed multiple files for this HVAC project. Now combine all findings into a final summary.

PROJECT: {project_name}
CLIENT: {client_name}

INDIVIDUAL FILE ANALYSES:
{combined_data[:20000]}

Create a comprehensive project summary combining all information found across files.
Prioritize the most specific/detailed values when files have conflicting info.

Return this exact JSON structure:
{{
    "summary": {{
        "project_name": "{project_name}",
        "client_name": "{client_name}",
        "contact_phone": "phone number or N/A",
        "contact_email": "email or N/A",
        "location": "full address or N/A",
        "project_type": "RNC/RREN/CNC/CREN/Bare RNC or N/A",
        "design_service": "Full Design/Basic/Bare/Manual J Only or N/A",
        "project_cost": "dollar amount or N/A",
        "total_area_sqft": "square footage or N/A",
        "system_type": "equipment type or N/A",
        "num_systems": "number or N/A",
        "fuel_type": "gas/electric/propane or N/A",
        "construction_type": "new/existing/renovation or N/A",
        "brand": "equipment brand or N/A",
        "seer": "SEER rating or N/A"
    }},
    "missing_info": [
        {{"item": "field name", "reason": "why it's missing"}}
    ],
    "notes": "important observations for the designer"
}}

Return ONLY valid JSON."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        ai_response = response.content[0].text.strip()
        
        import re
        if ai_response.startswith('```'):
            ai_response = ai_response.split('```')[1]
            if ai_response.startswith('json'):
                ai_response = ai_response[4:]
        
        json_match = re.search(r'\{[\s\S]*\}', ai_response)
        if json_match:
            return json.loads(json_match.group())
        return {'error': 'Could not parse final summary'}
        
    except Exception as e:
        print(f"[STREAM] Final combination failed: {e}")
        return {'error': str(e)}


def get_project_file_count(token, client_name, project_name, cached_clients):
    """Get file count and file list without downloading"""
    
    # Find client folder
    client_folder = None
    client_name_lower = client_name.lower()
    
    for folder in cached_clients:
        name = folder.get('attributes', {}).get('name', '')
        if name.lower() == client_name_lower:
            client_folder = folder
            break
    
    if not client_folder:
        # Try to find similar names to help user
        similar = [f.get('attributes', {}).get('name', '') for f in cached_clients 
                   if client_name_lower[:4] in f.get('attributes', {}).get('name', '').lower()][:3]
        if similar:
            return None, f"Couldn't find client folder '{client_name}' in WorkDrive. Did you mean: {', '.join(similar)}?"
        return None, f"Couldn't find client folder '{client_name}' in WorkDrive. Check the spelling or create the folder first."
    
    client_folder_id = client_folder.get('id')
    project_files = zoho.get_project_files_from_workdrive(token, client_folder_id, project_name)
    
    # Check if project folder was actually found (all lists empty means not found)
    all_empty = all(len(project_files.get(k, [])) == 0 for k in ['forms', 'files_from_client', 'working_drawings', 'emails'])
    if all_empty and not project_files.get('summary_form'):
        return None, f"Found client '{client_name}' but couldn't find project '{project_name}' inside. Check that the project folder name matches exactly."
    
    # Build list of downloadable files
    downloadable = []
    downloadable_extensions = ['.pdf', '.txt', '.msg', '.eml']
    
    for folder_key in ['forms', 'files_from_client', 'emails']:
        for f in project_files.get(folder_key, []):
            fname = f.get('attributes', {}).get('name', '')
            if any(fname.lower().endswith(e) for e in downloadable_extensions):
                downloadable.append({
                    'file_info': f,
                    'folder': folder_key,
                    'name': fname
                })
    
    if len(downloadable) == 0:
        return None, f"Found the project folder but no PDF, TXT, or email files to analyze. Upload the Summary Form and try again."
    
    return {
        'client_folder_id': client_folder_id,
        'files': downloadable,
        'total_count': len(downloadable),
        'file_count': {
            'forms': len(project_files.get('forms', [])),
            'files_from_client': len(project_files.get('files_from_client', [])),
            'working_drawings': len(project_files.get('working_drawings', [])),
            'emails': len(project_files.get('emails', []))
        }
    }, None
