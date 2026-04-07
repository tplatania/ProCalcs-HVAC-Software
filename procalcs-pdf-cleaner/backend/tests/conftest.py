"""
Shared test fixtures for procalcs-pdf-cleaner.
"""

import os
import sys
import pytest
import ezdxf

# Add backend to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def sample_dxf_path(tmp_path):
    """
    Create a sample DXF file with mixed entity types for testing.
    Simulates a typical architect-converted DWG with walls, doors,
    dimensions, text, furniture blocks, and appliance blocks.
    """
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    # --- GEOMETRY (should be KEPT) ---
    # Walls
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_lwpolyline([(0, 0), (0, 10), (10, 10)])
    # Door swing arc
    msp.add_arc(center=(3, 0), radius=2.5, start_angle=0, end_angle=90)
    # Column
    msp.add_circle(center=(5, 5), radius=0.5)

    # --- TEXT (should be STRIPPED) ---
    msp.add_text("LIVING ROOM", dxfattribs={'height': 0.5})
    msp.add_mtext("12'-6\" x 14'-0\"")

    # --- DIMENSIONS (should be STRIPPED) ---
    msp.add_aligned_dim(p1=(0, 0), p2=(10, 0), distance=1.0)

    # --- HATCH (should be STRIPPED) ---
    hatch = msp.add_hatch()
    hatch.paths.add_polyline_path([(0, 0), (2, 0), (2, 2), (0, 2)])

    # --- INSERT BLOCKS ---
    # Door block (should be KEPT)
    door_block = doc.blocks.new(name='DOOR_36')
    door_block.add_arc(center=(0, 0), radius=3, start_angle=0, end_angle=90)
    door_block.add_line((0, 0), (3, 0))
    msp.add_blockref('DOOR_36', insert=(3, 0))

    # Range hood block (should be KEPT — ventilation)
    hood_block = doc.blocks.new(name='RANGE_HOOD_30')
    hood_block.add_line((0, 0), (2.5, 0))
    hood_block.add_line((2.5, 0), (2.5, 2))
    msp.add_blockref('RANGE_HOOD_30', insert=(5, 8))

    # Dryer block (should be KEPT — ventilation)
    dryer_block = doc.blocks.new(name='DRYER_27')
    dryer_block.add_line((0, 0), (2.25, 0))
    msp.add_blockref('DRYER_27', insert=(8, 8))

    # Furniture block (should be STRIPPED)
    sofa_block = doc.blocks.new(name='SOFA_3SEAT')
    sofa_block.add_line((0, 0), (7, 0))
    msp.add_blockref('SOFA_3SEAT', insert=(2, 5))

    # Electrical symbol (should be STRIPPED)
    outlet_block = doc.blocks.new(name='ELEC_OUTLET_DUPLEX')
    outlet_block.add_circle(center=(0, 0), radius=0.2)
    msp.add_blockref('ELEC_OUTLET_DUPLEX', insert=(1, 3))

    # Toilet (should be STRIPPED)
    toilet_block = doc.blocks.new(name='TOILET_STD')
    toilet_block.add_circle(center=(0, 0), radius=0.5)
    msp.add_blockref('TOILET_STD', insert=(9, 2))

    # Unknown/generic block (should be KEPT per Richard's rule)
    mystery_block = doc.blocks.new(name='BLK_A7F2')
    mystery_block.add_line((0, 0), (1, 1))
    msp.add_blockref('BLK_A7F2', insert=(4, 4))

    # Save
    filepath = str(tmp_path / "test_plan.dxf")
    doc.saveas(filepath)
    return filepath


@pytest.fixture
def output_path(tmp_path):
    """Provide a temp path for cleaned output."""
    return str(tmp_path / "test_plan_clean.dxf")
