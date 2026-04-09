"""
client_profile.py — ClientProfile data model
Defines the structure of a per-client BOM profile.
Stored in Firestore. Managed by Richard and Windell via admin UI.
Follows ProCalcs Design Standards v2.0
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ===============================
# Sub-models
# ===============================

@dataclass
class SupplierInfo:
    """The distributor a client buys from and their pricing."""
    supplier_name: str = ""          # e.g. "Ferguson", "Winsupply"
    account_number: str = ""         # client's account number (optional)
    contact_name: str = ""           # optional rep / point-of-contact
    contact_email: str = ""          # optional contact email
    mastic_cost_per_gallon: float = 0.0
    tape_cost_per_roll: float = 0.0
    strapping_cost_per_roll: float = 0.0
    screws_cost_per_box: float = 0.0
    brush_cost_each: float = 0.0
    flex_duct_cost_per_foot: float = 0.0
    rect_duct_cost_per_sqft: float = 0.0


@dataclass
class MarkupTier:
    """A tiered markup rule applied above the default markup.

    Example: a "High Value" tier that applies 10% markup to line items
    between $5,000 and $20,000, overriding the flat default.
    """
    label: str = ""
    min_amount: float = 0.0
    max_amount: Optional[float] = None   # None = unbounded (Infinity)
    markup_percent: float = 0.0


@dataclass
class MarkupTiers:
    """Markup percentages applied by category."""
    equipment_pct: float = 0.0       # e.g. 15.0 = 15%
    materials_pct: float = 0.0       # duct, fittings, registers
    consumables_pct: float = 0.0     # mastic, tape, screws, etc.
    labor_pct: float = 0.0           # if labor is included


@dataclass
class BrandPreferences:
    """Preferred equipment and material brands per category."""
    ac_brand: str = ""               # e.g. "Carrier", "Goodman"
    furnace_brand: str = ""
    air_handler_brand: str = ""
    mastic_brand: str = ""           # e.g. "Rectorseal"
    tape_brand: str = ""             # e.g. "Nashua"
    flex_duct_brand: str = ""


@dataclass
class PartNameOverride:
    """Maps a ProCalcs standard part name to the client's preferred name/SKU."""
    standard_name: str = ""          # e.g. "4-inch collar"
    client_name: str = ""            # e.g. "4\" snap collar"
    client_sku: str = ""             # e.g. "FRG-COL-4IN"


# ===============================
# Main Model
# ===============================

@dataclass
class ClientProfile:
    """
    Full profile for one client (e.g. Beazer, D.R. Horton, Lennar).
    Stored as a Firestore document under collection: client_profiles.
    Document ID = client_id.
    """

    # Identity
    client_id: str = ""              # Unique ID — matches Designer Desktop client ID
    client_name: str = ""            # Display name e.g. "Beazer Homes"
    is_active: bool = True

    # Branding (UI-only — consumed by Designer Desktop, never by bom_service)
    brand_color: str = ""            # Hex color e.g. "#1e293b" for UI accent
    logo_url: str = ""               # URL to the client's logo image

    # Profile components
    supplier: SupplierInfo = field(default_factory=SupplierInfo)
    markup: MarkupTiers = field(default_factory=MarkupTiers)
    brands: BrandPreferences = field(default_factory=BrandPreferences)
    part_name_overrides: list = field(default_factory=list)  # list of PartNameOverride
    markup_tiers: list = field(default_factory=list)          # list of MarkupTier

    # Output preferences
    default_output_mode: str = "full"   # "full" | "materials_only" | "client_proposal" | "cost_estimate"
    include_labor: bool = False

    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: str = ""             # Email of Richard or Windell who created it
    notes: str = ""                  # Internal notes about this client's preferences


# ===============================
# Serialization Helpers
# ===============================

    def to_dict(self) -> dict:
        """Convert to Firestore-safe dictionary."""
        return {
            "client_id":           self.client_id,
            "client_name":         self.client_name,
            "is_active":           self.is_active,
            "brand_color":         self.brand_color,
            "logo_url":            self.logo_url,
            "supplier": {
                "supplier_name":           self.supplier.supplier_name,
                "account_number":          self.supplier.account_number,
                "contact_name":            self.supplier.contact_name,
                "contact_email":           self.supplier.contact_email,
                "mastic_cost_per_gallon":  self.supplier.mastic_cost_per_gallon,
                "tape_cost_per_roll":      self.supplier.tape_cost_per_roll,
                "strapping_cost_per_roll": self.supplier.strapping_cost_per_roll,
                "screws_cost_per_box":     self.supplier.screws_cost_per_box,
                "brush_cost_each":         self.supplier.brush_cost_each,
                "flex_duct_cost_per_foot": self.supplier.flex_duct_cost_per_foot,
                "rect_duct_cost_per_sqft": self.supplier.rect_duct_cost_per_sqft,
            },
            "markup": {
                "equipment_pct":   self.markup.equipment_pct,
                "materials_pct":   self.markup.materials_pct,
                "consumables_pct": self.markup.consumables_pct,
                "labor_pct":       self.markup.labor_pct,
            },
            "markup_tiers": [
                {"label":          t.label,
                 "min_amount":     t.min_amount,
                 "max_amount":     t.max_amount,
                 "markup_percent": t.markup_percent}
                for t in self.markup_tiers
            ],
            "brands": {
                "ac_brand":          self.brands.ac_brand,
                "furnace_brand":     self.brands.furnace_brand,
                "air_handler_brand": self.brands.air_handler_brand,
                "mastic_brand":      self.brands.mastic_brand,
                "tape_brand":        self.brands.tape_brand,
                "flex_duct_brand":   self.brands.flex_duct_brand,
            },
            "part_name_overrides": [
                {"standard_name": p.standard_name,
                 "client_name": p.client_name,
                 "client_sku": p.client_sku}
                for p in self.part_name_overrides
            ],
            "default_output_mode": self.default_output_mode,
            "include_labor":       self.include_labor,
            "created_at":          self.created_at,
            "updated_at":          self.updated_at,
            "created_by":          self.created_by,
            "notes":               self.notes,
        }

    @staticmethod
    def from_dict(data: dict) -> 'ClientProfile':
        """Build a ClientProfile from a Firestore document dictionary."""
        supplier_data = data.get('supplier', {})
        markup_data   = data.get('markup', {})
        brands_data   = data.get('brands', {})
        overrides_raw = data.get('part_name_overrides', [])
        tiers_raw     = data.get('markup_tiers', [])

        overrides = [
            PartNameOverride(
                standard_name=o.get('standard_name', ''),
                client_name=o.get('client_name', ''),
                client_sku=o.get('client_sku', '')
            )
            for o in overrides_raw
        ]

        tiers = []
        for t in tiers_raw:
            max_val = t.get('max_amount')
            tiers.append(MarkupTier(
                label=t.get('label', ''),
                min_amount=float(t.get('min_amount', 0.0) or 0.0),
                max_amount=(float(max_val) if max_val is not None else None),
                markup_percent=float(t.get('markup_percent', 0.0) or 0.0),
            ))

        return ClientProfile(
            client_id=data.get('client_id', ''),
            client_name=data.get('client_name', ''),
            is_active=data.get('is_active', True),
            brand_color=data.get('brand_color', ''),
            logo_url=data.get('logo_url', ''),
            supplier=SupplierInfo(
                supplier_name=supplier_data.get('supplier_name', ''),
                account_number=supplier_data.get('account_number', ''),
                contact_name=supplier_data.get('contact_name', ''),
                contact_email=supplier_data.get('contact_email', ''),
                mastic_cost_per_gallon=float(supplier_data.get('mastic_cost_per_gallon', 0.0)),
                tape_cost_per_roll=float(supplier_data.get('tape_cost_per_roll', 0.0)),
                strapping_cost_per_roll=float(supplier_data.get('strapping_cost_per_roll', 0.0)),
                screws_cost_per_box=float(supplier_data.get('screws_cost_per_box', 0.0)),
                brush_cost_each=float(supplier_data.get('brush_cost_each', 0.0)),
                flex_duct_cost_per_foot=float(supplier_data.get('flex_duct_cost_per_foot', 0.0)),
                rect_duct_cost_per_sqft=float(supplier_data.get('rect_duct_cost_per_sqft', 0.0)),
            ),
            markup=MarkupTiers(
                equipment_pct=float(markup_data.get('equipment_pct', 0.0)),
                materials_pct=float(markup_data.get('materials_pct', 0.0)),
                consumables_pct=float(markup_data.get('consumables_pct', 0.0)),
                labor_pct=float(markup_data.get('labor_pct', 0.0)),
            ),
            markup_tiers=tiers,
            brands=BrandPreferences(
                ac_brand=brands_data.get('ac_brand', ''),
                furnace_brand=brands_data.get('furnace_brand', ''),
                air_handler_brand=brands_data.get('air_handler_brand', ''),
                mastic_brand=brands_data.get('mastic_brand', ''),
                tape_brand=brands_data.get('tape_brand', ''),
                flex_duct_brand=brands_data.get('flex_duct_brand', ''),
            ),
            part_name_overrides=overrides,
            default_output_mode=data.get('default_output_mode', 'full'),
            include_labor=data.get('include_labor', False),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            created_by=data.get('created_by', ''),
            notes=data.get('notes', ''),
        )
