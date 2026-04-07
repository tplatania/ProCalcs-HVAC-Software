"""
Tests for the Smart INSERT Filter — block classification logic.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.insert_filter import (
    classify_block_by_name,
    get_filter_stats,
)


# ===============================
# Block Name Classification
# ===============================

class TestClassifyBlockByName:
    """Test keyword-based block classification."""

    def test_door_keywords_kept(self):
        assert classify_block_by_name('DOOR_36') == 'keep'
        assert classify_block_by_name('DR_INT_30') == 'keep'
        assert classify_block_by_name('Entry_Door') == 'keep'

    def test_ventilation_appliances_kept(self):
        assert classify_block_by_name('RANGE_HOOD_30') == 'keep'
        assert classify_block_by_name('DRYER_27') == 'keep'
        assert classify_block_by_name('EXHAUST_FAN') == 'keep'
        assert classify_block_by_name('VENT_DRYER') == 'keep'

    def test_furniture_stripped(self):
        assert classify_block_by_name('SOFA_3SEAT') == 'strip'
        assert classify_block_by_name('BED_QUEEN') == 'strip'
        assert classify_block_by_name('TABLE_DINING') == 'strip'
        assert classify_block_by_name('CHAIR_OFFICE') == 'strip'
        assert classify_block_by_name('DESK_60') == 'strip'

    def test_electrical_stripped(self):
        assert classify_block_by_name('ELEC_OUTLET_DUPLEX') == 'strip'
        assert classify_block_by_name('SWITCH_3WAY') == 'strip'
        assert classify_block_by_name('LIGHT_RECESSED') == 'strip'

    def test_plumbing_stripped(self):
        assert classify_block_by_name('TOILET_STD') == 'strip'
        assert classify_block_by_name('SINK_KITCHEN') == 'strip'
        assert classify_block_by_name('TUB_STANDARD') == 'strip'
        assert classify_block_by_name('SHOWER_48') == 'strip'

    def test_titleblock_and_misc_stripped(self):
        assert classify_block_by_name('TITLEBLOCK_24x36') == 'strip'
        assert classify_block_by_name('NORTH_ARROW') == 'strip'
        assert classify_block_by_name('SCALE_BAR') == 'strip'

    def test_non_ventilation_appliances_stripped(self):
        """Fridge, dishwasher, microwave are NOT ventilation-relevant."""
        assert classify_block_by_name('REFRIGERATOR_36') == 'strip'
        assert classify_block_by_name('DISHWASHER_24') == 'strip'
        assert classify_block_by_name('MICROWAVE_BUILT_IN') == 'strip'

    def test_unknown_blocks_return_unknown(self):
        assert classify_block_by_name('BLK_A7F2') == 'unknown'
        assert classify_block_by_name('X_12345') == 'unknown'
        assert classify_block_by_name('BLOCK_001') == 'unknown'

    def test_ambiguous_blocks_kept(self):
        assert classify_block_by_name('APPLIANCE_GENERIC') == 'keep'
        assert classify_block_by_name('MECH_EQUIP') == 'keep'

    def test_empty_and_none(self):
        assert classify_block_by_name('') == 'unknown'
        assert classify_block_by_name(None) == 'unknown'

    def test_case_insensitive(self):
        """Block names should match regardless of case."""
        assert classify_block_by_name('door_36') == 'keep'
        assert classify_block_by_name('DOOR_36') == 'keep'
        assert classify_block_by_name('Door_36') == 'keep'
        assert classify_block_by_name('SOFA_3seat') == 'strip'


# ===============================
# Filter Stats
# ===============================

class TestFilterStats:
    """Test the stats summary builder."""

    def test_stats_structure(self):
        stats = get_filter_stats(
            kept_blocks=['DOOR_36', 'DOOR_36', 'RANGE_HOOD_30'],
            stripped_blocks=['SOFA_3SEAT', 'TOILET_STD'],
            unknown_blocks=['BLK_A7F2']
        )
        assert stats['kept_count'] == 3
        assert stats['stripped_count'] == 2
        assert stats['unknown_kept_count'] == 1
        assert 'DOOR_36' in stats['kept_names']
        assert 'SOFA_3SEAT' in stats['stripped_names']

    def test_empty_stats(self):
        stats = get_filter_stats([], [], [])
        assert stats['kept_count'] == 0
        assert stats['stripped_count'] == 0
