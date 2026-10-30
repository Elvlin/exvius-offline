"""Verify New Game preserves the previous local save and uses fresh game state."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'source/server'))
from player_state import PlayerState
from offline_menu import new_game, status


class OfflineMenuTests(unittest.TestCase):
    def test_new_game_keeps_recovery_and_resets_progress(self):
        with tempfile.TemporaryDirectory(dir=PROJECT / 'source/build/android') as folder:
            path = Path(folder) / 'campaign.json'
            old = PlayerState.load('', slot='campaign')
            old.data['currencies']['lapis_free'] = 99
            self.assertTrue(old.save(str(path), force=True))
            state = SimpleNamespace(player=old, state_dirty=True)
            result = new_game(state, str(path), 'campaign')
            self.assertTrue(result['has_save'])
            self.assertEqual(state.player.data['currencies']['lapis_free'], 0)
            self.assertEqual(state.player.data['rank']['level'], 1)
            self.assertEqual(state.player.data['inventory']['items'], [])
            self.assertEqual(state.player.item_count(23, 180), 0)
            backups = list((path.parent / 'backups').glob('*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text())['currencies']['lapis_free'], 99)
            self.assertEqual(PlayerState.load(str(path)).data['currencies']['lapis_free'], 0)
            self.assertEqual(PlayerState.load(str(path)).data['inventory']['items'], [])

    def test_failed_new_save_keeps_current_player_and_file(self):
        with tempfile.TemporaryDirectory(dir=PROJECT / 'source/build/android') as folder:
            path = Path(folder) / 'campaign.json'
            old = PlayerState.load('', slot='campaign')
            self.assertTrue(old.save(str(path), force=True))
            before = path.read_bytes()
            state = SimpleNamespace(player=old, state_dirty=True)
            with patch.object(PlayerState, 'save', return_value=False):
                with self.assertRaises(OSError):
                    new_game(state, str(path), 'campaign')
            self.assertIs(state.player, old)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_save_disables_continue(self):
        self.assertFalse(status(SimpleNamespace(player=None), PROJECT / 'source/build/android/missing-save.json')['has_save'])


if __name__ == '__main__':
    unittest.main()
