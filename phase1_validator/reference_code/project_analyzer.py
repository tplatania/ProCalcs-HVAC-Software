"""
ProCalcs Project Analyzer
Analyzes project files and generates summaries + RFI emails
"""

import os
import json
from pathlib import Path
import PyPDF2
import anthropic

# Content extraction limits (characters)
MAX_RUP_TEXT_LENGTH = 5000      # Limit per .rup file for AI context
MAX_PDF_TEXT_LENGTH = 10000     # Limit per PDF for AI context
MAX_RUP_FILES_TO_PARSE = 3      # Max .rup files to include in analysis

class ProjectAnalyzer:
    def __init__(self, project_path):
        self.project_path = Path(project_path)
        self.project_data = {
            'name': self.project_path.name,
            'rup_files': [],
            'pdf_files': [],
            'emails': [],
            'excel_files': [],
            'all_text': []
        }
    
    def scan_project_files(self):
        """Scan and categorize all project files"""
        print(f"Scanning project: {self.project_path}")
        
        for root, dirs, files in os.walk(self.project_path):
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                
                if ext == '.rup':
                    self.project_data['rup_files'].append(str(file_path))
                elif ext == '.pdf':
                    self.project_data['pdf_files'].append(str(file_path))
                elif ext in ['.msg', '.eml']:
                    self.project_data['emails'].append(str(file_path))
                elif ext in ['.xlsx', '.xls']:
                    self.project_data['excel_files'].append(str(file_path))
        
        print(f"Found {len(self.project_data['rup_files'])} .rup files")
        print(f"Found {len(self.project_data['pdf_files'])} PDF files")
        print(f"Found {len(self.project_data['emails'])} email files")
        
        return self.project_data
    
    def parse_rup_file(self, rup_path):
        """Extract key data from .rup file"""
        try:
            with open(rup_path, 'rb') as f:
                data = f.read()
            
            # Decode UTF-16 (with null bytes)
            text = data.decode('utf-16-le', errors='ignore')
            
            # Extract key information
            info = {
                'file': os.path.basename(rup_path),
                'version': self._extract_between(text, 'VRSN=', '\r\n'),
                'timestamp': self._extract_between(text, 'TIMESTAMP=', '\r\n'),
                'raw_text': text[:MAX_RUP_TEXT_LENGTH]
            }
            
            return info
        except Exception as e:
            print(f"Error parsing {rup_path}: {e}")
            return None
    
    def parse_pdf_file(self, pdf_path):
        """Extract text from PDF - handles both text and form fields"""
        try:
            with open(pdf_path, 'rb') as f:
                pdf = PyPDF2.PdfReader(f)
                text = ""
                
                # Extract form field values if available
                fields = pdf.get_fields()
                if fields:
                    text += "=== PDF FORM FIELDS ===\n"
                    for name, field in fields.items():
                        value = field.get('/V', '')
                        if value and value != 'No value':
                            # Handle checkbox values
                            if value == '/On':
                                text += f"{name}: CHECKED\n"
                            elif value == '/Off':
                                pass  # Skip unchecked boxes
                            else:
                                text += f"{name}: {value}\n"
                    text += "\n=== END FORM FIELDS ===\n\n"
                
                # Extract regular text from ALL pages (not just 5)
                text += "=== PDF TEXT CONTENT ===\n"
                for i in range(len(pdf.pages)):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        text += f"\n--- Page {i+1} ---\n"
                        text += page_text
                
                text += "\n=== END PDF CONTENT ===\n"
            
            return {
                'file': os.path.basename(pdf_path),
                'text': text[:MAX_PDF_TEXT_LENGTH]
            }
        except Exception as e:
            print(f"Error parsing {pdf_path}: {e}")
            return None
    
    def _extract_between(self, text, start, end):
        """Helper to extract text between markers"""
        try:
            start_idx = text.find(start)
            if start_idx == -1:
                return None
            start_idx += len(start)
            end_idx = text.find(end, start_idx)
            if end_idx == -1:
                return None
            return text[start_idx:end_idx].strip()
        except Exception as e:
            print(f"Error extracting text between markers: {e}")
            return None
    
    def _find_project_folder(self, folder_name, alternate_names=None):
        """Find folder in project path, checking direct and nested structures.
        
        Args:
            folder_name: Primary folder name to look for
            alternate_names: Optional list of alternate folder names to try
        
        Returns:
            Path object if found, None otherwise
        """
        names_to_try = [folder_name]
        if alternate_names:
            names_to_try.extend(alternate_names)
        
        for name in names_to_try:
            # Try direct path
            folder = self.project_path / name
            if folder.exists():
                return folder
            
            # Try nested structure (project_path / project_name / folder)
            nested = self.project_path / self.project_path.name / name
            if nested.exists():
                return nested
        
        return None
    
    def extract_all_content(self):
        """Extract content from all files with priority order"""
        print("\nExtracting content from files...")
        
        # PRIORITY 1: Summary Form
        forms_folder = self._find_project_folder('Forms')
        if forms_folder:
            print("  [Priority 1] Looking for Summary Form...")
            for pdf_file in forms_folder.glob('*.pdf'):
                filename_lower = pdf_file.name.lower()
                if 'summary' in filename_lower or 'rfi' in filename_lower:
                    print(f"    Found: {pdf_file.name}")
                    info = self.parse_pdf_file(pdf_file)
                    if info:
                        self.project_data['all_text'].insert(0, f"CLIENT SUMMARY FORM (PRIMARY SOURCE):\n{info['text']}")
                    break  # Use first summary form found
        
        # PRIORITY 2: Files From Client (plans, specs, drawings)
        files_from_client = self._find_project_folder('Files From Client', ['Files from Client'])
        if files_from_client:
            print("  [Priority 2] Reading Files From Client...")
            for pdf_file in files_from_client.glob('*.pdf'):
                info = self.parse_pdf_file(pdf_file)
                if info:
                    self.project_data['all_text'].append(f"CLIENT FILE - {info['file']}:\n{info['text']}")
        
        # PRIORITY 3: Email Communications
        emails_folder = self._find_project_folder('Emails')
        if emails_folder:
            print("  [Priority 3] Reading Email Communications...")
            # Note: .msg files need special parsing, skipping for now
            # TODO: Add email parsing in future iteration
        
        # PRIORITY 4: Working Drawings (.rup files for additional context)
        working_drawings = self._find_project_folder('Working Drawings')
        if working_drawings:
            print("  [Priority 4] Reading Working Drawings...")
            for rup_file in list(working_drawings.glob('*.rup'))[:MAX_RUP_FILES_TO_PARSE]:
                info = self.parse_rup_file(rup_file)
                if info:
                    self.project_data['all_text'].append(f"DESIGN FILE - {info['file']}:\n{info['raw_text']}")
        
        print(f"Extracted {len(self.project_data['all_text'])} file contents")
        return self.project_data
    
    def generate_ai_summary(self, api_key):
        """Use Claude to generate project summary and identify missing info"""
        print("\nGenerating AI summary...")
        
        # Combine all extracted text
        combined_text = "\n\n---\n\n".join(self.project_data['all_text'])
        
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = f"""You are analyzing an HVAC design project. The client has submitted a project summary form and supporting documents.

Your task:
1. Extract all project information from the client's summary form and files
2. Identify what information is MISSING or UNCLEAR that we need FROM THE CLIENT
3. DO NOT flag items that:
   - We (ProCalcs) determine ourselves (supply/return locations, duct routing details)
   - Are already provided in architectural drawings in "Files From Client"
   - Are technical decisions we make during design

IMPORTANT CONTEXT:
- The "Completed-Project-Summary-Form" is what the CLIENT filled out
- "Files From Client" folder contains architectural drawings and specs they provided
- Check if architectural items (floor plans, elevations, etc.) are in the provided files before flagging as missing

Respond in THREE sections:

## PROJECT SUMMARY
JSON object with all known information:
```json
{{
  "project_name": "...",
  "client_name": "...",
  "client_email": "...",
  "building_type": "...",
  "total_area_sqft": "...",
  "floors": "...",
  "climate_zone": "...",
  "location": "...",
  "system_type": "...",
  "special_requirements": "...",
  "services_requested": ["..."]
}}
```

## MISSING INFORMATION
List ONLY items that are:
- Truly missing from client's submittal
- Client's responsibility to provide (not our design decisions)
- Critical for accurate load calculations

Format each as an object:
[
  {{"item": "Wall R-values", "reason": "Form shows 'None' - need insulation specs", "category": "building_specs"}},
  {{"item": "Project timeline", "reason": "Not specified", "category": "project_logistics"}}
]

Categories: building_specs, client_info, project_logistics, hvac_preferences

DO NOT INCLUDE:
- Supply/return outlet locations (we determine)
- Specific duct routing (we design)
- Equipment placement within mechanical rooms (we optimize)

## FILES PROVIDED
List what architectural/technical files were found in the submission.

---
CLIENT'S PROJECT FILES:
{combined_text[:20000]}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Save results
        results = {
            'project_name': self.project_data['name'],
            'ai_analysis': response_text
        }
        
        output_path = self.project_path / 'AI_Analysis_Results.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\nResults saved to: {output_path}")
        return results


# Test the analyzer
if __name__ == "__main__":
    # Import config for API key
    try:
        from config import Config
        API_KEY = Config.ANTHROPIC_API_KEY
    except ImportError:
        print("ERROR: Config module not found. Make sure .env is configured.")
        exit(1)
    
    project_path = r"D:\ProCalcs_Design_Process\Test_Project\Alys Beach FF-01"
    
    analyzer = ProjectAnalyzer(project_path)
    analyzer.scan_project_files()
    analyzer.extract_all_content()
    
    # Generate AI summary
    results = analyzer.generate_ai_summary(API_KEY)
    print("\n" + "="*60)
    print(results['ai_analysis'])
