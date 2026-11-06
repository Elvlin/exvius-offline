"""Platform-independent summon facade over the existing backend transactions."""
import copy
import os
from pathlib import Path
import sys
import threading

SERVER = Path(__file__).resolve().parents[2] / 'server'
_bound_root = None


class SummonError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SummonService:
    def __init__(self, data, save, *, demo=False, initial_lapis=0):
        global _bound_root
        root = Path(data).resolve()
        if _bound_root is not None and _bound_root != root:
            raise ValueError('Use a fresh process for another data root')
        if initial_lapis < 0:
            raise ValueError('Initial lapis must not be negative')
        for required in ('mst_decoded/F_UNIT_MST.ndjson', 'text_decoded/F_TEXT_UNITS_NAME.ndjson'):
            if not (root / required).is_file():
                raise ValueError('Missing backend data: ' + str(root / required))
        if 'player_state' in sys.modules and _bound_root is None:
            raise ValueError('Create the service before importing the legacy backend')
        os.environ.update(FFBE_DATA=str(root), MST_DIR=str(root / 'mst_decoded'),
                          TEXT_DIR=str(root / 'text_decoded'), GACHA_ONLY='all',
                          GACHA_CAMPAIGN='all', GACHA_STANDARD='1')
        sys.path.insert(0, str(SERVER))
        import player_state
        import ffbe_gacha
        _bound_root = root
        self.engine, self.gacha = player_state, ffbe_gacha
        self.save_path = Path(save).resolve()
        self.demo = demo
        self.lock = threading.RLock()
        self.player = player_state.PlayerState.load(str(self.save_path), slot='ios-summons', mode='live')
        if not self.save_path.exists():
            self.player.add_currency('lapis_free', initial_lapis)
            self._save()
        if demo:
            from demo_data import BANNER_IDS
            self.catalogue = {str(b['id']): copy.deepcopy(b) for b in ffbe_gacha.authored_banners()
                              if str(b['id']) in BANNER_IDS}
        else:
            self.catalogue = {str(b['id']): copy.deepcopy(b) for b in ffbe_gacha.all_banners()}

    def _save(self):
        if not self.player.save(str(self.save_path)):
            raise SummonError('save_failed', 'Campaign could not be saved; summon was not accepted.')

    def state(self):
        with self.lock:
            return copy.deepcopy({'demo_metadata': self.demo, 'currencies': self.player.currencies,
                                  'units': self.player.data['roster'],
                                  'last_pull': self.player.data['gacha'].get('last_pull')})

    def _banner(self, banner_id):
        try:
            return self.catalogue[str(banner_id)]
        except KeyError:
            raise SummonError('unknown_banner', 'Unknown banner') from None

    @staticmethod
    def _supported(banner):
        # Deliberately expose only currency-priced unit banners in this slice.
        # Ticket, box, step-up, and mixed reward paths stay in the existing backend.
        cost = banner.get('cost')
        return (isinstance(cost, dict) and cost.get('kind') in
                ('lapis', 'lapis_free', 'lapis_paid', 'friend_point', 'gil', 'free')
                and not any(banner.get(k) for k in ('steps', 'boxes', 'reward_pool', 'selection')))

    def banners(self):
        with self.lock:
            return [{'id': uid, 'name': b.get('name', uid), 'supported': bool(self._supported(b)),
                     'cost': copy.deepcopy(b.get('cost')), 'draws': b.get('draws', 1),
                     'offers': ['primary', 'secondary'] if b.get('secondary_offer') else ['primary']}
                    for uid, b in self.catalogue.items()]

    def details(self, banner_id, offer='primary'):
        with self.lock:
            b = self._banner(banner_id)
            selected = self._offer(b, offer) or b
            pool = self.engine.expand_pool(b)
            total = sum(max(0, float(row.get('rate', 0))) for row in pool)
            return copy.deepcopy({'id': str(b['id']), 'name': b.get('name'),
                'cost': selected.get('cost', b.get('cost')), 'draws': selected.get('draws', b.get('draws', 1)),
                'guarantee': selected.get('guarantee', b.get('guarantee', {})),
                'base_pool': [dict(row, name=self.gacha.unit_name(row['unit_id']),
                                   probability=float(row.get('rate', 0)) / total if total else 0)
                              for row in pool],
                'note': 'Base weights only; guarantees can alter final slot probabilities.'})

    @staticmethod
    def _offer(banner, offer):
        if offer == 'primary':
            return None
        if offer == 'secondary' and banner.get('secondary_offer'):
            return banner['secondary_offer']
        raise SummonError('invalid_offer', 'Choose an available primary or secondary offer')

    def summon(self, banner_id, offer='primary'):
        with self.lock:
            b = self._banner(banner_id)
            if not self._supported(b):
                raise SummonError('unsupported_banner', 'This banner needs a later interface extension')
            selected = self._offer(b, offer)
            before, dirty = copy.deepcopy(self.player.data), self.player.dirty
            try:
                result = self.player.roll_gacha(copy.deepcopy(b), repeats=1, offer=copy.deepcopy(selected))
                if result is None:
                    raise SummonError('summon_refused', 'Not enough currency, limit reached, or unavailable pool')
                self._save()
            except Exception:
                self.player.data, self.player.dirty = before, dirty
                raise
            result = copy.deepcopy(result)
            for award in result['awards']:
                award['name'] = self.gacha.unit_name(award['unit_id']) or award['unit_id']
            return {'result': result, 'state': self.state()}
