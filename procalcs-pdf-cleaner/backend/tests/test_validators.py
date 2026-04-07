"""
Tests for upload validation.
"""

import os
import sys
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.validators import validate_upload


class FakeFile:
    """Minimal file-like object for testing upload validation."""

    def __init__(self, filename='test.dxf', content=b'fake content'):
        self.filename = filename
        self._content = content
        self._position = 0

    def seek(self, pos, whence=0):
        if whence == 2:
            self._position = len(self._content)
        else:
            self._position = pos

    def tell(self):
        return self._position


class TestValidateUpload:
    """Test file upload validation."""

    def test_valid_dxf(self):
        result = validate_upload(FakeFile('plan.dxf'))
        assert result['is_valid'] is True
        assert result['extension'] == 'dxf'

    def test_valid_dwg(self):
        result = validate_upload(FakeFile('plan.dwg'))
        assert result['is_valid'] is True
        assert result['extension'] == 'dwg'

    def test_no_file(self):
        result = validate_upload(None)
        assert result['is_valid'] is False
        assert 'No file' in result['error']

    def test_no_filename(self):
        f = FakeFile('')
        result = validate_upload(f)
        assert result['is_valid'] is False

    def test_wrong_extension(self):
        result = validate_upload(FakeFile('plan.pdf'))
        assert result['is_valid'] is False
        assert 'not supported' in result['error']

    def test_oversized_file(self):
        # Create a fake file that reports 100MB
        big_file = FakeFile('plan.dxf', content=b'x' * (100 * 1024 * 1024))
        result = validate_upload(big_file)
        assert result['is_valid'] is False
        assert 'too large' in result['error']

    def test_case_insensitive_extension(self):
        result = validate_upload(FakeFile('PLAN.DXF'))
        assert result['is_valid'] is True

    def test_exe_rejected(self):
        result = validate_upload(FakeFile('malware.exe'))
        assert result['is_valid'] is False
