# ProCalcs Wrightsoft Default Template — Parsed Reference
### Source File: ProCalcs_Wrightsoft_Default_Template.rut
### Parsed: April 7, 2026 | Software: Right-Suite Universal v25.0.05 | Serial: RSU55661

---

## FILE OVERVIEW

This is the ProCalcs team's standardized Wrightsoft starting template. Every new job the
design team opens in Right-Suite Universal begins from these preloaded defaults. Understanding
what is baked in here is essential context for building the AI-powered BOM — because these
are the baseline assumptions the BOM must be aware of.

---

## CONTRACTOR IDENTITY (Pre-loaded on all proposals)

| Field | Value |
|---|---|
| Name | Tom Platania |
| Company | ProCalcs, LLC |
| City/State | Jensen Beach, FL 34957 |
| Phone | 772-882-5700 |
| Email | tom@procalcs.net |
| Website | www.ProCalcs.Net |
| License # | CAC1815254 (FL) |

---

## DEFAULT WEATHER LOCATION

| Field | Value |
|---|---|
| Primary Location | Tampa, FL |
| Weather Station | Tampa Intl AP (FL057) |
| Secondary Reference | Jacksonville, FL |

All new jobs default to Tampa, FL weather data. Designers change this per job.

---

## DEFAULT SYSTEM TYPE

All new jobs start with:
- **System:** AC + Furnace (Split AC + Gas Furnace)
- **SEER:** 0 (placeholder — designer selects actual equipment)
- **AFUE:** 80%
- **EF:** 0.60

Additional system types available in template:
- Split AC + Electric Strip Heat
- Split AC + Furnace (multiple configurations)

---

## DEFAULT EQUIPMENT TYPES (Pre-loaded stubs)

These are the equipment categories pre-loaded as starting points:

| # | Type |
|---|---|
| 1 | Split AC |
| 2 | Gas Furnace |
| 3 | Gas Water Heater |

Designers select actual brand/model/capacity per job from the equipment database.

---

## THERMOSTAT SCHEDULES (Pre-loaded)

| Schedule Name | Description |
|---|---|
| Clg75SetUp | Cooling 75°F night, 85°F day |
| Htg70 | Heating set point 70°F |
| Htg70SetBack | 70°F morning/evening, 65°F day/night |
| ResOccupancy | Typical residential occupancy pattern |
| ResActivity | Typical residential activity pattern |
| Clg75-AIP | Cooling set point 75°F (AIP version) |
| AlwaysOn | Standard office (always occupied) |

---

## DUCT DESIGN PREFERENCES

| Field | Value |
|---|---|
| Method | RectTrunk / RoundBranch — ProCalcs Standard |
| Description | Rectangular trunks with flex branches |
| Sizing Method | Equal Friction |

This is the ProCalcs standard duct layout method applied to every new job automatically.

---

## BUILDING DEFAULTS

| Field | Value |
|---|---|
| Building Type | Single Level |
| Duct Location | Ducts in Attic (Vented) |
| Insulation | Asphalt shingle, R-30 |
| System Mode | Heat/Cool |

---

## EQUIPMENT BRANDS / PART SOURCES (Loaded in BOM module)

These are the manufacturer part sources pre-loaded in the Right-Proposal/BOM module.
This tells us which brands ProCalcs already has parts data for in Wrightsoft:

| Code | Manufacturer |
|---|---|
| RTH | Rheem/Ruud |
| UNC | Unico |
| WSF | Wrightsoft Generic |
| QST | Quest |
| SAMP | Sample (template placeholder) |
| AMAN | AmanaF |
| GOOD | Goodman |
| BRYA | Bryant |
| CARR | Carrier |
| GREE | Gree Electric Appliances |
| LGEL | LG Electronics |
| MITS | Mitsubishi Electric |
| MRCL | MRCOOL |
| UPN | Uponor |
| FUJI | Fujitsu |
| DAIC | Daikin |

---

## PROPOSAL MODULE DEFAULTS

- **Report Label:** ProCalcs Cooling Disclaimer Test
- **ProCalcs appears as the contractor** on all proposal/BOM output
- Manufacturer logos and contact info pre-loaded for each brand above
- Wrightsoft (Lexington MA) also listed as a reference source

---

## CATALOG FILES LOADED (Accessory/Symbol Libraries)

The following drawing catalog files are linked in the template:
- Bath Appliances.cat
- Building Components.cat
- Kitchen Appliances.cat
(Additional catalogs in C:\ProgramData\Wrightsoft HVAC\Data\)

---

## REGISTER SCHEDULE

39 register/grille pairs are pre-defined in the template (REGSCH/REGSCHPAIR).
These map supply and return register types to duct sizes — relevant to BOM
auto-population of grille line items.

---

## KEY TAKEAWAYS FOR THE AI BOM BUILD

1. **Tampa FL is the default weather location** — jobs outside FL will always need weather
   override. The BOM should be aware of location as it may affect equipment specs.

2. **Rect trunk / flex branch is the ProCalcs standard** — this directly informs how the
   AI estimates duct material quantities (linear feet of rectangular duct vs. flex duct).

3. **16 manufacturer brands are pre-loaded** — the BOM has access to parts data for all
   of these brands. Client profiles should map preferred brands to these codes.

4. **Ducts in attic is the default** — relevant for estimating insulation, hanger straps,
   and support materials in the consumables layer of the BOM.

5. **Single Level is the default building type** — multi-story jobs will have different
   material estimates and should be flagged in the BOM logic.

6. **Tom Platania / ProCalcs LLC is the default contractor identity** — this appears on
   all proposal output. Client-specific profiles will need to preserve this while adding
   client-specific parts/pricing.

---

*Parsed from binary .rut format | For developer reference only*
*Original file: ProCalcs_Wrightsoft_Default_Template.rut*
