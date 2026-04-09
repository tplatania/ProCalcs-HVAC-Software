10-04-2026 Updates

🔧 In Progress:
Cleaning up loose ends from the MVP push — fixing a pricing rounding
edge case, extending the client profile model so branding and contact
fields stop getting dropped on save, and running live round-trip tests
against the staging environment before committing.

✅ Done Today

Project: ProCalcs Designer Desktop

1. Pricing Rounding Fix

Problem: The BOM engine was computing line-item totals from an
already-rounded unit price, which could lose a penny on values that
landed exactly on the banker's-rounding boundary. Reproducible example:
2 gallons of mastic at $18.50 with a 25% markup should come out to
$46.25, but the old math returned $46.24. Small error, real enough to
make totals look wrong on inspection.

Solution: Reordered the arithmetic so totals come from the full-
precision product and round only once at the end. Display values stay
rounded to 2 decimal places for presentation. The pre-existing failing
test now passes; all 44 tests in the suite are green.

2. Extended Client Profile Model

Problem: The Designer Desktop profile form collects five fields that
the Python model didn't have — brand color, logo URL, supplier
contact name and email, and tiered markup rules. The adapter silently
dropped all of them on save, so anything Richard or Windell typed into
those inputs vanished the moment they clicked Save. Cosmetic fields
for now, but the behavior looked buggy.

Solution: Added the missing fields to the Python client profile model
with full serialization round-trip support. Added a new markup tier
sub-model that accepts bounded ranges (e.g., $5,000–$20,000 at 10%)
and unbounded upper tiers (e.g., $20,000+ at 8%). The existing flat
markup percentages still drive actual BOM pricing — tiers are stored
and retrieved but not yet applied during pricing, which is a separate
product decision about how they should combine with the flat rates.

3. Adapter Threading

Problem: After extending the Python model, the Designer Desktop
adapter still had hardcoded defaults for the new fields. Extending
the model without updating the adapter would be a no-op from the
user's perspective.

Solution: Updated the adapter's flatten and unflatten functions to
thread all new fields through in both directions. On update, any
field the SPA didn't send is preserved from the existing record
instead of being overwritten with an empty value.

4. Test Suite Cleanup

Problem: The Python test suite couldn't run locally without installing
the full Anthropic and Google Cloud SDKs, because the BOM service
imports them at module load time. Every new developer hit the same
"No module named 'anthropic'" wall.

Solution: Added module shims in the shared pytest configuration so
the SDKs get mocked automatically at test collection time. Production
containers still use the real packages; the shims only kick in when
the real ones aren't installed. Full suite now runs green in a clean
local environment with zero setup.

5. Live Round-Trip Verification

Problem: The backlog changes touched both services at the same time.
Shipping git commits before proving the deployed code actually
round-trips the extended fields would have been dangerous — a
failure would only surface the next time someone edited a profile.

Solution: Deployed both services, then ran a live PUT against the
staging adapter with all five extended fields filled in, including a
two-tier markup example with an unbounded upper tier. Follow-up GET
confirmed every field persisted in Firestore and came back through
the adapter unchanged. Ten out of ten assertions passed.

6. BOM Generate Smoke Test (post-fix)

Problem: The rounding fix touches the critical pricing path. Any
silent regression here would corrupt every BOM generated during the
Richard/Tom demo.

Solution: Re-ran the full parse → generate flow against the live
staging URL with the Enos sample and the ProCalcs Direct profile.
Got 49 line items, $12,144.50 cost, $15,328.45 price. Ratio looks
right for Ferguson plus the 15/20/30 markup tiers. Pricing math is
behaving.

Latest branches:
origin/dev/rup-parsing, origin/main

Cloud Run state after today:
- procalcs-hvac-api       revision 00003-q25 (extended adapter)
- procalcs-hvac-bom       revision 00003-zqv (rounding fix + new model)
- procalcs-hvac-cleaner   unchanged

📅 ETA / Next Steps:
- Commit the remaining adapter change and push both branches. The
  backend bundle already landed as a focused commit earlier; only
  the Designer Desktop adapter edit is still uncommitted. (10 min)
- Browser eyeball the profile form — load ProCalcs Direct and confirm
  the brand color picker, logo URL, supplier contact, and markup
  tiers all show the values the round-trip test put in. No code
  changes expected. (15 min)
- Backfill Beazer Homes - Arizona with realistic extended-field
  values so the demo has two visually distinct profiles. (15 min)
- Wire markup tiers into actual pricing. Requires a product decision
  on whether tiers override or stack with the flat markup, and
  whether they apply per line item or per category subtotal. (half
  day once the decision is made)
- JSON textarea "Advanced" toggle on BOM Engine from the Gerald spec
  — nice dev ergonomic, not on the demo path. (1 hour)
- Job history persistence and a "my previous BOMs" view. Bigger
  feature, needs Firestore schema. (1–2 days)

⚠️ Blockers: None
