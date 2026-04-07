"""
Tests for the DXF cleanup engine.
Uses the sample_dxf_path fixture from conftest.py which creates
a realistic DXF with walls, doors, text, dimensions, furniture,
and ventilation appliances.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import ezdxf
from services.cleaner_service import clean_dxf


# ===============================
# Core Cleanup Tests
# ===============================

class TestCleanDxf:
    """Test the main DXF cleanup engine."""

    def test_cleanup_succeeds(self, sample_dxf_path, output_path):
        result = clean_dxf(sample_dxf_path, output_path)
        assert result['success'] is True
        assert os.path.exists(output_path)

    def test_geometry_preserved(self, sample_dxf_path, output_path):
        """Walls (LINE, LWPOLYLINE), arcs, circles must survive."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        entity_types = [e.dxftype() for e in msp]
        assert 'LINE' in entity_types
        assert 'LWPOLYLINE' in entity_types
        assert 'ARC' in entity_types
        assert 'CIRCLE' in entity_types

    def test_text_stripped(self, sample_dxf_path, output_path):
        """TEXT and MTEXT must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        entity_types = [e.dxftype() for e in msp]
        assert 'TEXT' not in entity_types
        assert 'MTEXT' not in entity_types

    def test_dimensions_stripped(self, sample_dxf_path, output_path):
        """DIMENSION entities must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        entity_types = [e.dxftype() for e in msp]
        assert 'DIMENSION' not in entity_types

    def test_hatch_stripped(self, sample_dxf_path, output_path):
        """HATCH entities must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        entity_types = [e.dxftype() for e in msp]
        assert 'HATCH' not in entity_types

    def test_door_block_kept(self, sample_dxf_path, output_path):
        """Door INSERT blocks must survive cleanup."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'DOOR_36' in insert_names

    def test_ventilation_appliances_kept(self, sample_dxf_path, output_path):
        """Range hood and dryer INSERT blocks must survive."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'RANGE_HOOD_30' in insert_names
        assert 'DRYER_27' in insert_names

    def test_furniture_stripped(self, sample_dxf_path, output_path):
        """Furniture INSERT blocks must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'SOFA_3SEAT' not in insert_names

    def test_electrical_stripped(self, sample_dxf_path, output_path):
        """Electrical INSERT blocks must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'ELEC_OUTLET_DUPLEX' not in insert_names

    def test_plumbing_stripped(self, sample_dxf_path, output_path):
        """Plumbing INSERT blocks must be removed."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'TOILET_STD' not in insert_names

    def test_unknown_block_kept(self, sample_dxf_path, output_path):
        """Unknown blocks kept per Richard's rule."""
        clean_dxf(sample_dxf_path, output_path)
        doc = ezdxf.readfile(output_path)
        msp = doc.modelspace()

        insert_names = [
            e.dxf.name for e in msp if e.dxftype() == 'INSERT'
        ]
        assert 'BLK_A7F2' in insert_names

    def test_stats_returned(self, sample_dxf_path, output_path):
        """Result should include entity counts and INSERT filter stats."""
        result = clean_dxf(sample_dxf_path, output_path)
        assert 'kept_count' in result
        assert 'stripped_count' in result
        assert 'insert_filter' in result
        assert result['kept_count'] > 0
        assert result['stripped_count'] > 0
