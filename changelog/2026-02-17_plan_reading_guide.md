# 2026-02-17 — Created Plan Reading Guide

## What
Created PLAN_READING_GUIDE.md — the AI's training manual for reading architectural
floor plans. Located in shared/plan_reading_guide/ so every phase references it.

## Sections
1. Dimension String Hierarchy (outermost=overall, innermost=openings)
2. Window & Door Callouts (centerline vs room dimensions)
3. Room Dimensions (where they appear, what they measure)
4. Conditioned vs Unconditioned Space (indicators, tricky spaces)
5. Line Types (solid, dashed, hatching meanings)
6. Common Symbols (doors, windows, sections, HVAC)
7. Common Abbreviations (TYP, SIM, CMU, R.O., etc.)
8. Cross-Check Rules (4 math checks to catch errors)
9. Known AI Mistakes (GT Bray lessons: window centerline, misread dims, wrong rooms)
10. Commercial vs Residential Differences
11. Step-by-Step Reading Process (8 steps)

## Why
Testing Opus 4.6 on GT Bray plans revealed the AI makes the same mistakes as Gemini:
grabbing window centerline callouts as room widths, misreading overall dimensions,
and misidentifying unconditioned rooms. This guide prevents those errors by teaching
the AI how architects actually dimension plans.

## Key Lesson
The information to read plans correctly is ON the plans — construction notes,
dimension string hierarchy, leader arrows. The AI doesn't need fancy logic,
it needs to read what's there the way a human designer does.

## Requested By
Tom
