# Ask Your HVAC Pro - Master Project Document

## Last Updated: December 28, 2025 (Late Evening)

---

# 📱 APP OVERVIEW

| Item | Value |
|------|-------|
| App Name | Ask Your HVAC Pro |
| Version | 1.0.3+1 |
| Package (iOS) | com.hbox.hvacAnswersApp |
| Package (Android) | com.hbox.hvacanswers |
| Framework | Flutter 3.5.3 |
| State Management | GetX |

---

# 🔗 INFRASTRUCTURE

### Backend Server (DEVELOPER CONTROLLED)
- **URL**: `https://backend-hvac-answer.hboxdigital.website`
- **Owner**: hboxdigital (developers)
- **Status**: Active, serving the live app
- **Action Needed**: Migrate to Tom's own server

### Firebase (TOM'S ACCOUNT)
- Used for: Authentication (Google/Apple Sign-In)
- Config files in project: `google-services.json`, `GoogleService-Info.plist`

### OpenAI (TOM'S ACCOUNT)
- **Platform**: https://platform.openai.com/assistants
- **Model**: GPT-4.1 (upgraded from GPT-4o)
- **Temperature**: 0.7
- **4 Assistants**:
  - Homeowners: `asst_ArVzRrP9NhWdWjDffHm4eDMt`
  - HVAC Contractors: `asst_ow6dqxhI34wAimm4eu6POANG`
  - Builders: `asst_xH0NA9862oHmuJ8Xsd6vhh54`
  - Architects: `asst_IVFHtg3ZFv6w2hRqsqjtckSa`

### ElevenLabs (TOM'S ACCOUNT)
- **Platform**: https://elevenlabs.io
- **Voice**: "Tom real voice"
- **Voice ID**: `9PhQHUzIMHSkxLs0SSsp`
- **Current Model**: `eleven_turbo_v2_5` (should change to `eleven_flash_v2_5`)

---

# 💰 SUBSCRIPTION PRODUCTS

### Pricing
- **Homeowner**: $9.99/month
- **Professional**: $24.90/month
- **Professional Yearly**: $249/year

### iOS Product IDs
- `com.hbox.hvacAnswersApp.basicmonthly`
- `com.hbox.hvacAnswersApp.basicyearly`
- `com.hbox.hvacAnswersApp.promonthly`
- `com.hbox.hvacAnswersApp.proyearly`

### Android Product IDs
- `com.hbox.hvacanswersapp.basicmonthly`
- `com.hbox.hvacanswersapp.basicyearly`
- `com.hbox.hvacanswersapp.promonthly`
- `com.hbox.hvacanswersapp.proyearly`

---

# 📲 APP STORE STATUS

### Apple App Store
- **Account Owner**: Tom ✅
- **App Status**: Live (minimal downloads)
- **Action Needed**: Get signing certificates from developers

### Google Play Store
- **Account Owner**: Tom ✅
- **App Status**: Awaiting approval
- **Action Needed**: Get keystore file and passwords from developers

---

# ✅ COMPLETED - KNOWLEDGE BASE (No App Update Required)

## OpenAI Assistant Improvements
All 4 assistants updated:

1. **Upgraded to GPT-4.1** - Latest model available for Assistants
2. **Temperature set to 0.7** - More consistent, accurate responses
3. **Max results set to 20** - Thorough file search

## Knowledge Files - ALL UPLOADED ✅
Location: `D:\ProCalcs_Design_Process\hvac_knowledge\`

### Core Files (All 4 Assistants)
| File | Lines | Description | Status |
|------|-------|-------------|--------|
| `all_building_codes.json` | ~500 | All 50 states residential & commercial codes | ✅ Uploaded |
| `hvac_diagnostics_professional.json` | ~300 | PT charts, superheat/subcool, fault signatures | ✅ Uploaded |
| `hvac_diagnostics_homeowner.json` | ~200 | Simplified diagnostics for homeowners | ✅ Uploaded |
| `manual_j_load_calculations.json` | ~250 | Manual J education + ProCalcs promotion | ✅ Uploaded |
| `hvac_manufacturers.json` | ~400 | Model decoders, warranties, known issues | ✅ Uploaded |
| `regional_hvac_considerations.json` | ~200 | Location-aware advice for all 50 states | ✅ Uploaded |
| `hvac_safety_protocols.json` | ~240 | Gas leak, CO, electrical hazard protocols | ✅ Uploaded |
| `mini_split_error_codes.json` | ~179 | 10 major brands with troubleshooting | ✅ Uploaded |
| `electrical_troubleshooting.json` | ~295 | Capacitors, contactors, amp draws, safety | ✅ Uploaded |
| `refrigerant_retrofit_guide.json` | ~208 | R-22 phase-out, retrofit options, R-454B | ✅ Uploaded |
| `hvac_maintenance_checklists.json` | 512 | Seasonal, annual, professional checklists | ✅ Uploaded |
| `repair_vs_replace_guide.json` | 846 | Cost analysis, decision framework, regional | ✅ Uploaded |

### Specialized Files
| File | Lines | Description | Uploaded To |
|------|-------|-------------|-------------|
| `hvac_for_builders.json` | ~226 | Builder-specific coordination & rough-in | ✅ Builders Only |
| `hvac_for_architects.json` | ~256 | Architect-specific design integration | ✅ Architects Only |

**Total Knowledge Base: ~4,600+ lines of expert HVAC content**

## System Instructions Added (All 4 Assistants)

### Base Instructions (All Assistants)
- No rule of thumb sizing (refuses "sq ft per ton" estimates)
- ProCalcs promotion with smart mention rules
- Regional & climate awareness
- Safety & emergency protocols
- Mini-split error code support

### Builder-Specific Instructions
- Construction coordination focus
- Rough-in timing and requirements
- Chase sizing and framing guidance
- Trade coordination triggers
- Key motto: "It's cheaper to move a line on paper than a duct in a finished wall."

### Architect-Specific Instructions
- Design integration focus
- Space planning, acoustics, aesthetics
- Phase-aware advice (SD/DD/CD/CA)
- Energy code and sustainability awareness
- Key motto: "Form follows function, but function requires space."

---

# 📋 CHANGES REQUIRING APP UPDATE

## UI/UX Changes

### 1. Onboarding Screen 1 - NEEDS COMPLETE REDESIGN
- **Current**: Generic robot illustration, feels cold and uninviting
- **Requested**: More welcoming design that connects with users

### 2. Onboarding Screen 2 - NEEDS COMPLETE REDESIGN
- **Current**: Generic businessman illustration
- **Requested**: More relevant, professional design

### 3. Onboarding Screen 3 - NEEDS COMPLETE REDESIGN
- **Current**: Generic person on couch with laptop
- **Requested**: More relevant, professional design

### 4. Login Screen - MINOR IMPROVEMENTS
- "Let's login to your account" → Change to "Welcome back"
- Add Apple Sign-In button (required by Apple)
- Add subtle background gradient

### 5. Settings Screen - MULTIPLE ISSUES
- "Setting" → "Settings" (grammar)
- Show subscription status
- Fix "Upgrade to Plus" showing for premium subscribers
- Add profile picture upload option
- Add way to edit name

### 6. About Us Screen - MINOR IMPROVEMENTS
- Add company info or contact details
- Add link to Terms of Service / Privacy Policy
- Add app version number

### 7. Subscription Screen - ACCESS ISSUES
- Add admin/owner account type
- Add ability for free/comp accounts

### 8. Navigation - MISSING NEW CHAT BUTTON
- No "New Chat" button in drawer menu (Android)
- Note: Button IS visible on iOS

### 9. Navigation - "Ask Your HVAC Pro" NOT CLICKABLE (BUG)
- Tapping "Ask Your HVAC Pro" in drawer does nothing

---

## AI/Voice Changes

### 10. Voice Input - SLOW END-OF-SPEECH DETECTION
- **Issue**: Microphone keeps listening 6 seconds after user stops talking
- **Expected**: Should detect silence within 1-2 seconds
- **Impact**: Total response ~9-11 seconds, could be 5-7 seconds with fix

### 11. ElevenLabs Voice Settings - UPDATE MODEL AND SETTINGS
- **Current Model**: eleven_turbo_v2_5 → **Change to**: eleven_flash_v2_5
- **Current Similarity**: 0.8 → **Change to**: 0.9
- **Current Stability**: 0.5 → **Change to**: 0.7 (fixes stutter)
- **Files**: `constants.dart`, `elevenlabs_service.dart`

### 12. ElevenLabs Architecture - SWITCH TO AGENT/WIDGET
- Current: Voice settings hardcoded in app
- **Recommended**: Switch to ElevenLabs Conversational AI Agent
- **Benefit**: Control voice settings from dashboard without app updates

---

## Security Changes

### 13. API Keys in Client Code
- **Issue**: OpenAI and ElevenLabs API keys hardcoded in `constants.dart`
- **Risk**: Keys can be extracted from the app
- **Fix**: Move API calls to backend server

---

# 🔮 FUTURE ENHANCEMENTS

## Additional Knowledge Files (Optional)
- Tool recommendations during diagnostics
- Brand-specific installation guides
- Ductwork design basics

---

# 📁 PROJECT LOCATIONS

### App Code
```
D:\Projects\Ask-Your-HVAC-Pro
```

### Knowledge Files
```
D:\ProCalcs_Design_Process\hvac_knowledge\
```

### Building Codes
```
D:\ProCalcs_Design_Process\building_codes\
```

---

# 📄 KEY FILES REFERENCE

```
lib/
├── helper/
│   ├── chatBotController.dart    # AI chat logic, Assistant routing
│   ├── constants.dart            # API keys, URLs (SENSITIVE)
│   ├── elevenlabs_Service.dart   # Voice TTS
│   ├── localStorage.dart         # User data, preferences
│   └── speechController.dart     # Speech-to-text
├── service/
│   ├── app_service.dart          # All backend API calls
│   ├── firebase.dart             # Firebase init
│   └── in_app_purchase_service.dart  # Subscriptions
├── model/
│   ├── userModel.dart            # User data structure
│   └── messageModel.dart         # Chat message structure
└── view/
    ├── home_page/
    │   ├── homepage_view.dart    # Main chat screen
    │   └── voiceScreen/          # Voice chat mode
    └── selectpersonality/        # User type selection
```

---

# 🛠️ DEVELOPMENT SETUP

### Requirements
- Flutter SDK 3.5.3+
- Android Studio (for emulators)
- Xcode (for iOS, Mac only)
- VS Code (recommended IDE)

### To Run Locally
```bash
cd D:\Projects\Ask-Your-HVAC-Pro
flutter pub get
flutter run
```

---

# 🔑 ITEMS NEEDED FROM DEVELOPERS

### For iOS Builds
- [ ] Distribution Certificate (.p12 file)
- [ ] Certificate password
- [ ] Push Notification Certificate
- [ ] Provisioning Profiles

### For Android Builds
- [ ] Keystore file (.keystore or .jks)
- [ ] key.properties file with passwords

### For Backend Migration
- [ ] Database schema/export
- [ ] API documentation
- [ ] Server-side code

---

# 📞 CONTACTS

### Developers
- Company: hboxdigital
- GitHub: dev-hbox

### ProCalcs
- Phone: 772-882-5700
- Email: tom@procalcs.net

---

# 📝 CHANGE LOG

### December 28, 2025 (Late Evening)
- ✅ Created `hvac_maintenance_checklists.json` (512 lines) - merged best of Gemini + ChatGPT
- ✅ Created `repair_vs_replace_guide.json` (846 lines) - comprehensive decision framework
- ✅ Uploaded ALL remaining knowledge files to OpenAI Assistants
- ✅ Knowledge base complete: 14 files, ~4,600+ lines of expert HVAC content

### December 28, 2025 (Evening)
- Created 7 knowledge files (regional, safety, mini-split, builders, architects, electrical, refrigerant)
- Updated system instructions for all 4 assistants
- Added builder-specific and architect-specific instructions

### December 28, 2025 (Earlier)
- Upgraded all 4 assistants to GPT-4.1
- Uploaded 5 initial knowledge files (codes, diagnostics, manufacturers, Manual J)
- Added ProCalcs promotion system instructions
- Added "no rule of thumb" sizing instruction
- Tested and verified AI responses working correctly
- Documented 13 changes requiring app update
