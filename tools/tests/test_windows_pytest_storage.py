from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.windows_pytest_storage import allocate


class ShortStorageTests(unittest.TestCase):
    def test_atomic_distinct_project_directories_and_collision_preserve(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'.verify';parent.mkdir()
            first=parent/'aa';first.mkdir();(first/'retained').write_text('history')
            with patch('tools.windows_pytest_storage.secrets.token_hex',side_effect=['aa','bb','cc']):
                second=allocate(parent);third=allocate(parent)
            self.assertEqual(second.name,'bb');self.assertEqual(third.name,'cc')
            self.assertEqual((first/'retained').read_text(),'history')
            self.assertEqual(second.parent,parent.resolve())

    def test_unrelated_or_missing_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):allocate(directory)
            with self.assertRaises(ValueError):allocate(Path(directory)/'.verify')
