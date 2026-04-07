# ProCalcs BOM
## AI-Powered Bill of Materials Service
### Version 1.0.0 | April 2026

---

## What This Is

A standalone web service that generates AI-powered Bills of Materials for
HVAC job designs. Lives in the ProCalcs ecosystem alongside Designer Desktop.
Gerald integrates by calling a single API endpoint.

## Tech Decisions

| Layer | Choice | Why |
|---|---|---|
| Backend | Python / Flask | ProCalcs standard. Blueprints keep routes clean. |
| AI | Anthropic Claude API | Reasons through design data to estimate full material list |
| Database | Google Firestore | Document model fits client profiles well. Fast reads. |
| Hosting | Google Cloud Run | ProCalcs standard. Stateless, scales to zero. |
| Frontend | React + Vite | Complex multi-view admin UI for Richard/Windell |

## Architecture

```
Designer Desktop
      |
      | POST /api/v1/bom/generate
      v
procalcs-bom (Cloud Run)
      |
      +-- profile_service  →  Firestore (client profiles)
      |
      +-- bom_service      →  Anthropic Claude API
      |
      +-- output_formatter →  Returns structured BOM JSON
```

## Project Structure

```
procalcs-bom/
├── .env.example              # Copy to .env.local for local dev
├── Dockerfile                # Cloud Run deployment
├── README.md                 # This file
├── backend/
│   ├── app.py                # Flask app factory
│   ├── config.py             # Centralized config — single source of truth
│   ├── requirements.txt      # Python dependencies
│   ├── routes/
│   │   ├── health_routes.py  # GET /health
│   │   ├── profile_routes.py # CRUD /api/v1/profiles
│   │   └── bom_routes.py     # POST /api/v1/bom/generate
│   ├── services/
│   │   ├── bom_service.py    # AI BOM generation logic (TODO)
│   │   ├── profile_service.py# Firestore profile CRUD (TODO)
│   │   └── output_formatter.py # BOM JSON → formatted output (TODO)
│   ├── models/
│   │   └── client_profile.py # ClientProfile data model (TODO)
│   ├── utils/
│   │   └── validators.py     # Input validation helpers (TODO)
│   └── tests/
│       └── test_bom.py       # pytest suite (TODO)
└── frontend/
    └── src/
        ├── components/       # Reusable UI components
        ├── pages/            # ProfileManager, BOMViewer
        ├── context/          # Auth context
        ├── hooks/            # Custom React hooks
        ├── utils/            # apiFetch wrapper, helpers
        └── styles/           # CSS
```

## API Reference

### Health Check
```
GET /health
Response: { "success": true, "data": { "status": "healthy" } }
```

### Generate BOM
```
POST /api/v1/bom/generate
Body: {
  "client_id": "beazer-001",
  "job_id": "job-12345",
  "design_data": {
    "duct_runs": [...],
    "fittings": [...],
    "equipment": [...],
    "registers": [...],
    "building": { "type": "single_level", "duct_location": "attic" }
  }
}
```

### Profile Management
```
GET    /api/v1/profiles/              List all profiles
GET    /api/v1/profiles/:client_id   Get one profile
POST   /api/v1/profiles/             Create profile
PUT    /api/v1/profiles/:client_id   Update profile
DELETE /api/v1/profiles/:client_id   Delete profile
```

## Local Development

```bash
# 1. Clone
git clone https://github.com/tplatania/ProCalcs-HVAC-Software.git
cd procalcs-bom

# 2. Backend setup
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. Environment
cp ../.env.example ../.env.local
# Fill in your keys in .env.local

# 4. Run backend
python app.py
# → http://localhost:5000/health

# 5. Frontend setup (separate terminal)
cd ../frontend
npm install
npm run dev
# → http://localhost:5173
```

## Deploy to Cloud Run

```bash
gcloud run deploy procalcs-bom --source . --region us-east1
```

Set environment variables in the Cloud Run console — never in code.

## Standards

This project follows ProCalcs Design Standards v2.0.
See `docs/DESIGN_STANDARDS.md` in the main ProCalcs repo.

- snake_case Python, PascalCase React components
- No file over 300 lines
- All API responses: `{ "success": bool, "data": {}, "error": "msg" }`
- try/except on every endpoint
- No credentials in code — environment variables only
- Use `logging` module, not `print()`

## Status

| Component | Status |
|---|---|
| Folder structure | ✅ Done |
| Config + app factory | ✅ Done |
| Health endpoint | ✅ Done |
| Route placeholders | ✅ Done |
| Client Profile service | 🔲 Next |
| BOM AI engine | 🔲 Next |
| Output formatter | 🔲 Next |
| Admin UI (React) | 🔲 Next |
| BOM Viewer UI | 🔲 Next |
| Tests | 🔲 Next |

---
*ProCalcs LLC | tom@procalcs.net | April 2026*
