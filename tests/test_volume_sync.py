import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from main import _sync_external_system_volume


class SystemVolumeSyncTests(unittest.TestCase):
    def setUp(self):
        self.hud = SimpleNamespace(volume_levels_signal=MagicMock())
        self.tools = SimpleNamespace(
            get_system_master_volume=MagicMock(return_value=62),
            player=SimpleNamespace(volume=84),
        )

    def test_external_system_volume_change_updates_both_slider_levels(self):
        result = _sync_external_system_volume(self.hud, self.tools, 40)

        self.assertEqual(result, 62)
        self.hud.volume_levels_signal.emit.assert_called_once_with(62, 84)

    def test_unchanged_or_unavailable_system_volume_does_not_emit_update(self):
        result = _sync_external_system_volume(self.hud, self.tools, 62)

        self.assertEqual(result, 62)
        self.hud.volume_levels_signal.emit.assert_not_called()

        self.tools.get_system_master_volume.return_value = None
        result = _sync_external_system_volume(self.hud, self.tools, 62)

        self.assertEqual(result, 62)
        self.hud.volume_levels_signal.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
