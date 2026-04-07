"""
Smart INSERT Filter — Block Reference Classification

Determines which INSERT (block reference) entities to keep vs strip.
Interior doors and ventilation-relevant appliances are preserved.
Everything else (furniture, electrical, plumbing) gets stripped.

Richard's Rule: When in doubt, keep it. A designer can delete an extra
block in seconds. Losing a needed door costs minutes of rework.
"""

import logging

logger = logging.getLogger('pdf_cleaner')


# ===============================
# Block Name Keyword Lists
# ===============================

# Keywords that indicate a block should be KEPT
KEEP_KEYWORDS = [
    'door', 'dr', 'entry', 'exit',
    'range', 'hood', 'rangehood', 'range_hood',
    'dryer', 'dry', 'vent_dryer',
    'exhaust', 'vent',
]

# Keywords that indicate a block should be STRIPPED
STRIP_KEYWORDS = [
    'furn', 'chair', 'table', 'bed', 'sofa', 'couch', 'desk',
    'cabinet', 'shelf', 'bookcase', 'dresser', 'nightstand',
    'elec', 'outlet', 'switch', 'light', 'lamp', 'recept',
    'panel', 'junction', 'gfci',
    'sink', 'toilet', 'tub', 'shower', 'lav', 'wc', 'bath',
    'faucet', 'bidet',
    'north', 'arrow', 'compass',
    'title', 'titleblock', 'border', 'legend',
    'scale', 'scalebar',
    'tree', 'plant', 'shrub', 'landscap',
    'car', 'vehicle', 'parking',
    'person', 'figure', 'human',
    'refrig', 'fridge', 'dishwash', 'microwave', 'oven',
    'washer',
]

# Ambiguous keywords — could go either way, default to KEEP
# per Richard's rule
AMBIGUOUS_KEYWORDS = [
    'appliance', 'equip', 'mech', 'hvac',
]


def classify_block_by_name(block_name):
    """
    Classify an INSERT block reference by its block definition name.
    Returns 'keep', 'strip', or 'unknown'.

    Uses case-insensitive keyword matching against the block name.
    """
    if not block_name:
        return 'unknown'

    name_lower = block_name.lower().strip()

    # Check KEEP keywords first — doors and ventilation win
    for keyword in KEEP_KEYWORDS:
        if keyword in name_lower:
            logger.debug("Block '%s' matched KEEP keyword '%s'", block_name, keyword)
            return 'keep'

    # Check STRIP keywords
    for keyword in STRIP_KEYWORDS:
        if keyword in name_lower:
            logger.debug("Block '%s' matched STRIP keyword '%s'", block_name, keyword)
            return 'strip'

    # Check ambiguous — default to keep per Richard's rule
    for keyword in AMBIGUOUS_KEYWORDS:
        if keyword in name_lower:
            logger.debug(
                "Block '%s' matched AMBIGUOUS keyword '%s' — keeping",
                block_name, keyword
            )
            return 'keep'

    # No keyword match — unknown
    return 'unknown'


def should_keep_insert(entity):
    """
    Determine if an INSERT entity should be kept in the cleaned output.

    Strategy:
    1. Check block name against keyword lists
    2. If unknown, default to KEEP (Richard's rule)

    Returns True if the entity should be preserved.
    """
    block_name = entity.dxf.name if entity.dxf.name else ''
    classification = classify_block_by_name(block_name)

    if classification == 'keep':
        return True
    elif classification == 'strip':
        return False
    else:
        # Unknown block — keep it. Designer can delete in seconds.
        # Losing something they needed costs real rework time.
        logger.info(
            "Unknown block '%s' — keeping per Richard's rule",
            block_name
        )
        return True


def get_filter_stats(kept_blocks, stripped_blocks, unknown_blocks):
    """
    Build a summary of what the INSERT filter did.
    Useful for the API response so designers know what happened.
    """
    return {
        "kept_count": len(kept_blocks),
        "stripped_count": len(stripped_blocks),
        "unknown_kept_count": len(unknown_blocks),
        "kept_names": list(set(kept_blocks)),
        "stripped_names": list(set(stripped_blocks)),
        "unknown_names": list(set(unknown_blocks)),
    }
