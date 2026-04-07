"""
DXF/DWG Cleanup Engine

Core service that reads a DXF file, strips non-essential entities,
preserves wall geometry + doors + ventilation appliances, and outputs
a clean file ready for Wrightsoft import.

Entity filtering rules:
  KEEP:   LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE
  FILTER: INSERT (via Smart INSERT Filter — doors/appliances kept)
  STRIP:  DIMENSION, TEXT, MTEXT, HATCH, everything else
"""

import os
import logging
import ezdxf

from config import Config
from services.insert_filter import should_keep_insert, get_filter_stats

logger = logging.getLogger('pdf_cleaner')


# ===============================
# Entity Type Classification
# ===============================

# Geometry types — always kept (walls, stairs, doors, windows, columns)
KEEP_ENTITY_TYPES = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE'}

# Always stripped — no exceptions
STRIP_ENTITY_TYPES = {'DIMENSION', 'TEXT', 'MTEXT', 'HATCH', 'LEADER', 'MLEADER'}

# INSERT entities go through the Smart INSERT Filter
FILTERED_ENTITY_TYPES = {'INSERT'}


def clean_dxf(input_path, output_path):
    """
    Read a DXF file, strip non-essential entities, write clean output.

    Args:
        input_path: Path to the source DXF file
        output_path: Path to write the cleaned DXF file

    Returns:
        dict with success status, stats, and any errors
    """
    try:
        doc = ezdxf.readfile(input_path)
    except Exception as e:
        logger.error("Failed to read DXF file %s: %s", input_path, e)
        return {
            "success": False,
            "error": f"Could not read file: {e}"
        }

    msp = doc.modelspace()

    # Track what we do for the response
    kept_count = 0
    stripped_count = 0
    kept_blocks = []
    stripped_blocks = []
    unknown_blocks = []
    entities_to_delete = []

    # ===============================
    # Classify Every Entity
    # ===============================
    for entity in msp:
        entity_type = entity.dxftype()

        if entity_type in KEEP_ENTITY_TYPES:
            # Geometry — always keep
            kept_count += 1

        elif entity_type in STRIP_ENTITY_TYPES:
            # Junk — always strip
            entities_to_delete.append(entity)
            stripped_count += 1

        elif entity_type in FILTERED_ENTITY_TYPES:
            # INSERT — run through Smart INSERT Filter
            block_name = entity.dxf.name if entity.dxf.name else 'unnamed'

            if should_keep_insert(entity):
                kept_count += 1
                kept_blocks.append(block_name)
            else:
                entities_to_delete.append(entity)
                stripped_count += 1
                stripped_blocks.append(block_name)

        else:
            # Unknown entity type — strip to keep file lean
            # Wrightsoft performance degrades with clutter
            entities_to_delete.append(entity)
            stripped_count += 1

    # ===============================
    # Delete Stripped Entities
    # ===============================
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            logger.warning("Could not delete entity: %s", e)

    # ===============================
    # Write Clean Output
    # ===============================
    try:
        doc.saveas(output_path)
    except Exception as e:
        logger.error("Failed to write clean DXF to %s: %s", output_path, e)
        return {
            "success": False,
            "error": f"Could not save cleaned file: {e}"
        }

    insert_stats = get_filter_stats(kept_blocks, stripped_blocks, unknown_blocks)

    logger.info(
        "Cleanup complete: kept %d, stripped %d, INSERT filter: %s",
        kept_count, stripped_count, insert_stats
    )

    return {
        "success": True,
        "kept_count": kept_count,
        "stripped_count": stripped_count,
        "insert_filter": insert_stats,
        "output_path": output_path
    }


def clean_dwg_file(upload_path):
    """
    Main entry point called by the route.
    Handles the full pipeline: DWG→DXF→clean→DXF→DWG

    For now (Phase 1), accepts DXF directly since ODA converter
    setup is environment-dependent. DWG conversion added when
    ODA is configured.

    Args:
        upload_path: Path to the uploaded DWG or DXF file

    Returns:
        dict with success, output_path, output_filename, and stats
    """
    filename = os.path.basename(upload_path)
    name, ext = os.path.splitext(filename)
    ext_lower = ext.lower()

    clean_name = f"{name}_clean.dxf"
    output_path = os.path.join(Config.TEMP_FOLDER, clean_name)

    if ext_lower == '.dxf':
        # Direct DXF processing
        result = clean_dxf(upload_path, output_path)

    elif ext_lower == '.dwg':
        # DWG requires ODA conversion: DWG→DXF→clean→DXF→DWG
        if not Config.ODA_CONVERTER_PATH:
            return {
                "success": False,
                "error": "DWG processing requires ODA File Converter. "
                         "Please configure ODA_CONVERTER_PATH or upload a DXF file."
            }
        # TODO: Implement ODA DWG→DXF conversion
        # For now, return not-yet-supported
        return {
            "success": False,
            "error": "DWG conversion coming soon. Please upload a DXF file for now."
        }
    else:
        return {
            "success": False,
            "error": f"Unsupported file type: {ext}"
        }

    if result.get('success'):
        result['output_filename'] = clean_name

    return result
