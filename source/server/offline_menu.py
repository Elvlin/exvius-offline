"""Local title-menu actions using the existing persistent PlayerState format."""
from pathlib import Path
import shutil
import threading
import time

from player_state import PlayerState

STATE_LOCK = threading.RLock()


def status(state, state_file):
    player = state.player
    return {
        'has_save': Path(state_file).is_file() and player is not None,
        'name': player.data['identity']['handle_name'] if player else '',
        'rank': player.data['rank']['level'] if player else 1,
    }


def new_game(state, state_file, slot):
    destination = Path(state_file)
    fresh = PlayerState.load('', slot=slot, mode='live')
    # The upstream harness seeds ticket 180 for its focused summon fixture.
    # A player's New Game must not inherit those test resources.
    test_tickets = fresh.item_count(23, 180)
    if test_tickets and not fresh.spend_item(23, 180, test_tickets):
        raise RuntimeError('The fresh-save test ticket seed could not be removed')
    fresh.data['inventory']['items'] = [row for row in fresh.data['inventory']['items']
                                       if (row['item_type'], row['item_id']) != (23, 180)]
    fresh.data.setdefault('meta', {})['offline_started'] = True
    if destination.exists():
        recovery = destination.parent / 'backups'
        recovery.mkdir(exist_ok=True)
        backup = recovery / (destination.stem + '-' + str(time.time_ns()) + '.json')
        shutil.copyfile(destination, backup)
    if not fresh.save(str(destination), force=True):
        raise OSError('The new local save could not be written. The previous save is preserved.')
    state.player = fresh
    state.state_dirty = False
    return status(state, state_file)
