"""Exercise the original encrypted handler and save pipeline without networking."""
import calendar
import time
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'source/server'))


class LocalGameIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='local-game-', dir=PROJECT / 'source/build')
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.root = Path(cls.fixture.name)
        for key in list(os.environ):
            if key.startswith(('FFBE_', 'GACHA_', 'STATE_', 'OUT_', 'CDN_', 'EVENT_', 'FRIENDS_')):
                os.environ.pop(key)
        for key, relative in (
            ('MST_DIR', 'mst_decoded'), ('TEXT_DIR', 'text_decoded'),
            ('ART_ROOT', 'cpk_extract'), ('VERSION_TABLE_XML', 'client/shared_prefs/gamedata.xml'),
            ('COMMUNITY_ART_ROOT', 'gacha_community/art')
        ):
            os.environ[key] = str(PROJECT / 'data' / relative)
        cls.local_file = cls.root / 'client/files/local-fixture.bin'
        cls.local_file.parent.mkdir(parents=True)
        cls.local_file.write_bytes(b'Local content fixture\x00\xff')
        # The saved Global cache's English summon banners, as the Android build bundles them.
        import shutil
        shutil.copytree(PROJECT / 'data/client/files/en/sd/static_banner/gacha',
                        cls.root / 'client/files/en/sd/static_banner/gacha')
        shutil.copytree(PROJECT / 'data/overlay/en/sd/area', cls.root / 'overlay/en/sd/area')
        cls.cached_banner = cls.root / 'client/files/en/sd/static_banner/gacha/main/exvius-cache-lookup.png'
        cls.cached_banner.parent.mkdir(parents=True, exist_ok=True)
        cls.cached_banner.write_bytes((PROJECT / 'source/server/assets/banner_art/'
                                      'daily_login_banner_dailylogin_00.png').read_bytes())

        def no_network(event, args):
            if event in {'socket.__new__', 'socket.bind', 'socket.connect', 'socket.getaddrinfo'}:
                raise AssertionError('Local game attempted networking: ' + event)

        sys.addaudithook(no_network)
        from local_game import LocalGame
        cls.game = LocalGame(cls.root, slot='localtest')
        cls.endpoints = json.loads((PROJECT / 'source/server/endpoints.json').read_text())['by_class']

    def setUp(self):
        from player_state import PlayerState
        state = self.game.server.State
        state.player = PlayerState.load('')
        state.state_dirty = False
        self.state_file = self.root / 'state/localtest.json'
        state.player.save(str(self.state_file), force=True)

    def restored_player(self):
        from player_state import PlayerState
        return PlayerState.load(str(self.state_file))

    def test_fresh_campaign_does_not_skip_opening_or_clear_first_stage(self):
        from ffbe_config import SWITCH_BASE_INDICES
        self.assertEqual(SWITCH_BASE_INDICES, ())
        player = self.game.server.State.player
        reply = self.exchange('InitializeRequest', {})
        row = next(r for rows in reply.values() if isinstance(rows, list)
                   for r in rows if isinstance(r, dict) and r.get('5opcUT9t') == '101')
        login = self.exchange('GetUserInfoRequest', {})
        self.assertEqual(login['8J1R5PXG'], reply['8J1R5PXG'])
        for index in (0, 117):
            digit, bit = divmod(index, 4)
            self.assertFalse(int(row['juA0Z4m7'][digit], 16) & (8 >> bit))
        self.assertEqual(player.data['progress']['cleared_missions'], [])
        self.load_mission('1110100')
        self.assertEqual(player.data['progress']['cleared_missions'], [])
        self.assertNotIn(0, player.switches['101'])
        self.assertNotIn(117, player.switches['101'])

    def test_login_preserves_existing_opening_and_story_progress(self):
        player = self.game.server.State.player
        player.grant_switch('101', 0)
        player.grant_switch('101', 117)
        player.data['progress']['cleared_missions'] = ['1110100', '1110101']
        player.save(str(self.state_file), force=True)
        self.game.server.State.player = player = self.restored_player()
        self.exchange('GetUserInfoRequest', {})
        self.assertTrue({0, 117}.issubset(player.switches['101']))
        self.assertEqual(player.data['progress']['cleared_missions'], ['1110100', '1110101'])

    def test_friend_pages_use_local_profiles_and_search_without_state_changes(self):
        from ffbe_friends import load_friends
        friend = str(load_friends()[0]['friend_id'])
        self.exchange('FriendListRequest', {})
        player = self.game.server.State.player
        before = copy.deepcopy(player.data)
        detail = self.exchange('FriendDetailRequest', {'I53AVzSo': [
            {'m3Wghr1j': friend, 'K3BV17gk': '1'}]})
        self.assertIn(friend, {row['m3Wghr1j'] for row in detail['2vuhy0Ex']})
        result = self.exchange('FriendSearchRequest', {'I53AVzSo': [{'m3Wghr1j': friend}]})
        self.assertEqual([row['m3Wghr1j'] for row in result['2K05IxtX']], [friend])
        self.assertEqual(result['2K05IxtX'][0]['K3BV17gk'], '4')
        detail = self.exchange('FriendDetailRequest', {'I53AVzSo': [
            {'m3Wghr1j': friend, 'K3BV17gk': '4'}]})
        self.assertEqual(detail['2vuhy0Ex'][0]['K3BV17gk'], '4')
        missing = self.exchange('FriendSearchRequest', {'I53AVzSo': [{'m3Wghr1j': '000000000'}]})
        self.assertEqual(missing['2K05IxtX'], [])
        self.exchange('FriendSuggestRequest', {})
        self.assertEqual(player.data, before)

    def test_local_friends_are_ready_before_the_first_companion_request(self):
        from ffbe_friends import load_friends
        expected = {str(friend['friend_id']) for friend in load_friends()}
        reply = self.exchange('GetUserInfoRequest', {})
        self.assertEqual({row['m3Wghr1j'] for row in reply['56gJBnVh']}, expected)

    def test_friend_favorite_persists_without_changing_units_or_currencies(self):
        from ffbe_friends import load_friends
        friend = str(load_friends()[0]['friend_id'])
        player = self.game.server.State.player
        before_roster, before_currency = copy.deepcopy(player.data['roster']), copy.deepcopy(player.currencies)
        result = self.exchange('FriendFavoriteRequest', {'I53AVzSo': [
            {'m3Wghr1j': friend, '8zE6w9RP': '1'}]})
        row = next(row for row in result['2vuhy0Ex'] if row['m3Wghr1j'] == friend)
        self.assertEqual(row['8zE6w9RP'], '1')
        self.assertTrue(self.restored_player().data['exvius_friends']['favorites'][friend])
        self.assertEqual(player.data['roster'], before_roster)
        self.assertEqual(player.currencies, before_currency)

    def summon(self, banner_id, detail_id, repeats=1, ticket_id=0):
        return self.exchange('GachaExeRequest', {'5yLD4dYI': [{
            'X1IuZnj2': str(banner_id), 'nqzG3b2v': str(detail_id),
            '2RtVPS3b': str(repeats), 'zJ1A6HXm': str(ticket_id)}]})

    def load_mission(self, mission_id, expected_status=200):
        return self.exchange('DungeonResourceLoadMstListRequest', {
            '1zTjkp5B': [{'6uIYE15X': str(mission_id)}]}, expected_status=expected_status)

    def finish_mission(self, mission_id, cleared=True, damage=None):
        report = {
            'jQsE54Iz': [{'qo3PECw6': str(mission_id)}],
            '2urzfX6d': [{'69ieJGhD': '1:1:3' if cleared else '', 'Z1p0j9uF': '0'}],
            'L4i4418y': [{'6q35TL07': '0'}]}
        if damage is not None:
            report['nSG9Jb1s'] = [{'NYb0Cri6': 'TOTAL_DAMAGE', '6gAX1BpC': str(damage)}]
        return self.exchange('MissionEndRequest', report)

    def daily_login(self, date):
        import time
        original = time.strftime
        def local_date(format, *args):
            if format == '%Y-%m-%d':
                return date
            if format == '%Y%m%d':
                return date.replace('-', '')
            return original(format, *args)
        with patch('ffbe_player.time.strftime', side_effect=local_date):
            return self.exchange('LoginBonusRequest', {})

    def daily_mails(self):
        return [mail for mail in self.game.server.State.player.mailbox if mail.get('daily_login')]

    def exchange(self, name, plaintext, expected_status=200):
        import ffbe_crypto as crypto
        endpoint = self.endpoints[name]
        request_id, key = endpoint['request_id'], endpoint['encode_key']
        envelope = {
            'TEAYk6R1': {'z5hB3P01': request_id, 'ytHoz4E2': '1', '9K0Pzcpd': '1166'},
            't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(
                crypto.key16(key), json.dumps(plaintext).encode(), double_pad=True)}
        }
        response = self.game.request('POST', '/lapisProd/app/php/gme/actionSymbol/' +
                                     endpoint['url_token'] + '.php', json.dumps(envelope))
        self.assertEqual(response.status, expected_status)
        self.assertEqual(int(response.headers['Content-Length']), len(response.body))
        if expected_status != 200:
            return response
        state = self.game.server.State
        reply_key = request_id if state.reply_key == 'reqid' else request_id[:8] if state.reply_key == 'reqid8' else key
        ciphertext = json.loads(response.body)['t7n6cVWf']['qrVcDe48']
        raw = crypto.cbc_decrypt(crypto.key16(reply_key), ciphertext)
        padding = raw[-1] if raw else 0
        if 1 <= padding <= 16 and raw[-padding:] == bytes([padding]) * padding:
            raw = raw[:-padding]
        return json.loads(raw)

    def test_encrypted_game_setting_uses_existing_handler(self):
        reply = self.exchange('GameSettingRequest', {'LhVz6aD2': [{'9qh17ZUf': 'Rain'}]})
        self.assertIsInstance(reply, dict)
        self.assertTrue(reply)

    def test_rookie_equipment_claims_pay_once_and_survive_reload(self):
        import ffbe_player as quests
        player = self.game.server.State.player
        gil = player.currencies['gil']
        units = len(player.data['roster'])
        for qid in ('100101', '100102', '100103'):
            meta = quests._quest_index()[qid]
            player.bump_progress(quests._progress_key('spchallenge', '1001', qid), meta['max'])
        for qid in ('100101', '100102', '100103'):
            request = {'Dtw7GU1j': [{'fK3W9qYA': 10011, 'zF6QIY2r': 1001, 'V36ygRYs': int(qid)}]}
            reply = self.exchange('SpChallengeRewardGetRequest', request)
            row = next(r for r in reply['3KLU4mSD'] if r['V36ygRYs'] == qid)
            self.assertEqual(row['QCLs6SV8'], '1')
            self.assertEqual(self.restored_player().progress_value('claimed/1001/' + qid), 1)
            paid = copy.deepcopy(player.data)
            self.exchange('SpChallengeRewardGetRequest', request)
            self.assertEqual(player.data, paid, 'Retrying the same claim must not pay twice')
        self.assertEqual(player.currencies['gil'], gil + 30000)
        self.assertEqual(len(player.data['roster']), units + 20)
        status = next(r for r in reply['WS1g0ECn'] if r['zF6QIY2r'] == '1001')
        self.assertEqual(status['es0Yun3Z'], '0')

    def test_rookie_claim_rejects_a_different_schedule_without_paying(self):
        self.exchange('GetUserInfoRequest', {})
        player = self.game.server.State.player
        player.bump_progress('spchallenge/1001/100101', 1)
        before = copy.deepcopy(player.data)
        self.exchange('SpChallengeRewardGetRequest', {'Dtw7GU1j': [
            {'fK3W9qYA': 11011, 'zF6QIY2r': 1101, 'V36ygRYs': 100101}]})
        self.assertEqual(player.data, before)

    def test_all_permanent_challenge_rewards_are_claimable_through_native_requests(self):
        import ffbe_player as quests
        player = self.game.server.State.player
        picked = quests.sp_challenge_picked()
        count = 0
        for gid, rows in picked:
            for row in rows:
                qid = str(row['V36ygRYs'])
                meta = quests._quest_index()[qid]
                player.bump_progress(quests._progress_key('spchallenge', gid, qid), meta['max'])
                request = {'Dtw7GU1j': [{'fK3W9qYA': int(quests.sp_schedule_id(gid)),
                                        'zF6QIY2r': int(gid), 'V36ygRYs': int(qid)}]}
                reply = self.exchange('SpChallengeRewardGetRequest', request)
                with self.subTest(quest=qid, reward=row['dX6cor8j']):
                    info = next(r for r in reply['3KLU4mSD'] if r['V36ygRYs'] == qid)
                    self.assertEqual(info['QCLs6SV8'], '1')
                    self.assertEqual(self.restored_player().progress_value('claimed/' + gid + '/' + qid), 1)
                count += 1
        self.assertEqual(count, 49)

    def test_all_visible_panel_quest_rewards_pay_and_keep_other_panels(self):
        import ffbe_player as quests
        player = self.game.server.State.player
        table = quests.panel_quest_tables()
        for gid, group in quests.panel_quest_picked():
            rows = table['quests'][gid]
            for row in rows:
                qid = str(row['V36ygRYs'])
                player.bump_progress('panelquest/' + gid + '/' + qid, int(row['oz5Vt6AR']))
            for row in rows:
                qid = str(row['V36ygRYs'])
                request = {'QxrSeO56': [{'fK3W9qYA': group['fK3W9qYA'],
                                         'zF6QIY2r': gid, 'V36ygRYs': qid}]}
                reply = self.exchange('sgPanelQuestRewardRequest', request)
                with self.subTest(quest=qid):
                    info = next(r for r in reply['ELPwhZj0'] if r['V36ygRYs'] == qid)
                    self.assertEqual(info['QCLs6SV8'], '1')
                    self.assertEqual(len(reply['ELPwhZj0']), len(rows))
                    paid = copy.deepcopy(player.data)
                    self.exchange('sgPanelQuestRewardRequest', request)
                    self.assertEqual(player.data, paid)

    def test_every_bundle_tile_has_a_downloaded_icon(self):
        reply = self.exchange('BundleStatusRequest', {})
        for row in reply['fMohhKK8']:
            with self.subTest(bundle=row['EzXXHtTY']):
                self.assertTrue(row.get('cSUSxGZA'))
                icon = PROJECT / 'data/client/files/common_lang/sd/static_banner/bundle' / row['cSUSxGZA']
                self.assertTrue(icon.is_file(), str(icon))

    def test_home_vortex_archive_is_available_without_granting_story_espers(self):
        from player_state import _load_ndjson, switch_position
        player = self.game.server.State.player
        before = copy.deepcopy(player.data.get('beasts'))
        self.exchange('GetUserInfoRequest', {})
        feature = _load_ndjson('F_FUNCTION_MST.ndjson', 'G1nfeht7')['FUNCTION_REEL_DIMENSION']
        kind, bit = switch_position(feature['juA0Z4m7'])
        self.assertIn(bit, player.switches[kind])
        self.assertEqual(player.data.get('beasts'), before)

    def test_daily_claim_and_claim_all_pay_once(self):
        import ffbe_player as quests
        self.exchange('SpChallengeEntryRequest', {})
        player = self.game.server.State.player
        day = player.daily_quest_day()
        ids = player.daily_quest_ids()
        self.assertTrue(ids)
        for qid in ids:
            target = int(quests.daily_quest_by_id()[qid]['target'])
            player.bump_progress(player.daily_progress_key(qid, day), target)
        self.exchange('DailyQuestClaimRewardRequest', {'vj87UqEd': [{'nYD7LvSG': ids[0]}]})
        self.assertEqual(player.progress_value(player.daily_claim_key(ids[0], day)), 1)
        reply = self.exchange('DailyQuestClaimAllRewardRequest', {})
        self.assertTrue(all(player.progress_value(player.daily_claim_key(qid, day)) == 1 for qid in ids))
        self.assertTrue(all(int(row['ZLuw4DLa']) == 2 for row in reply['Hqdgx83H']))
        paid = copy.deepcopy(player.data)
        self.exchange('DailyQuestClaimAllRewardRequest', {})
        self.assertEqual(player.data, paid)

    def test_medal_purchase_encrypted_roundtrip_and_reloaded_limits(self):
        state = self.game.server.State
        state.player.grant_item(20, 106200100, 40)
        state.player.save(str(self.state_file), force=True)
        stores = self.exchange('VariableStoreCheckRequest', {})['3VS1Bhmf']
        self.assertEqual([(r['Z20mNDvL'], r['za2xsDj5'], r['suR36Jpm']) for r in stores],
                         [('900104', '7000458', '20:106200100'),
                          ('900122', '900105', '20:106300100')])
        before = len(state.player.data['roster'])
        request = {'2d6RAkvh': [{'Z20mNDvL': '7000458', 'L2gHC5ta': '230701:1'}]}
        reply = self.exchange('MedalExchangeRequest', request)
        self.assertEqual(state.player.item_count(20, 106200100), 20)
        self.assertEqual(len(state.player.data['roster']), before + 1)
        self.assertEqual(reply['R5kozET8'], [{'S21FT3L8': '230701', 'ngQX7a3N': '1'}])
        state.player = self.restored_player()
        self.assertEqual(state.player.data['exvius_medal_exchange']['counts']['230701'], 1)
        refreshed = self.exchange('GetUserInfoRequest', {})
        self.assertEqual(refreshed['R5kozET8'], reply['R5kozET8'])
        self.exchange('MedalExchangeRequest', request)
        self.assertEqual(state.player.item_count(20, 106200100), 0)
        self.assertEqual(len(state.player.data['roster']), before + 2)
        self.exchange('MedalExchangeRequest', request)
        self.assertEqual(state.player.item_count(20, 106200100), 0)
        self.assertEqual(len(state.player.data['roster']), before + 2)
        self.assertEqual(self.restored_player().data['exvius_medal_exchange']['counts']['230701'], 2)

    def test_existing_summon_spends_once_and_persists_award(self):
        from player_state import PlayerState
        state = self.game.server.State
        state.player.currencies['friend_point'] = 1000
        state_file = self.root / 'state/localtest.json'
        state.player.save(str(state_file), force=True)
        before = len(state.player.data['roster'])
        reply = self.exchange('GachaExeRequest', {'5yLD4dYI': [
            {'X1IuZnj2': '1', 'nqzG3b2v': '10011', '2RtVPS3b': '1'}]})
        self.assertTrue(reply.get('5yLD4dYI'))
        self.assertEqual(state.player.currencies['friend_point'], 800)
        self.assertEqual(len(state.player.data['roster']), before + 1)
        restored = PlayerState.load(str(state_file))
        self.assertEqual(restored.currencies['friend_point'], 800)
        self.assertEqual(len(restored.data['roster']), before + 1)

    def test_existing_content_handler_reads_local_bytes(self):
        response = self.game.request('GET', '/local-fixture.bin')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, self.local_file.read_bytes())

    def test_local_web_post_reads_content_and_never_returns_a_game_envelope(self):
        for path, expected in [('/local-fixture.bin', self.local_file.read_bytes()),
                               ('/en/content/userpolicysin/index_a.html',
                                (PROJECT / 'source/server/webcontent/userpolicy.html').read_bytes())]:
            response = self.game.request('POST', path, b'platform=Android&player=local',
                                         {'Content-Type': 'application/x-www-form-urlencoded'})
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, expected)
        missing = self.game.request('POST', '/content/exvius-missing.html', b'player=local')
        self.assertEqual(missing.status, 404)
        self.assertEqual(missing.body, b'')

    def test_local_art_lookup_serves_existing_images_and_missing_files(self):
        from ffbe_gacha import area_art_index, banner_art_index
        for category, index in [('banner', banner_art_index()), ('area', area_art_index())]:
            name, path = next((name, path) for name, path in index.items()
                              if name.lower().endswith('.png'))
            response = self.game.request('GET', '/' + category + '/' + name)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, Path(path).read_bytes())
            missing = self.game.request('GET', '/' + category + '/exvius-missing-test-image.png')
            self.assertEqual(missing.status, 404)
            self.assertEqual(missing.body, b'')

        cached = self.game.request('GET', '/banner/common_lang/sd/static_banner/gacha/main/' +
                                   self.cached_banner.name)
        self.assertEqual(cached.status, 200)
        self.assertEqual(cached.body, self.cached_banner.read_bytes())

    def test_existing_banner_entry_and_refresh_include_selected_archive_section(self):
        from ffbe_gacha import all_banners
        from gacha_archive import visible_banners
        self.assertGreater(len(all_banners()), 400)
        expected = {str(b['id']) for b in visible_banners(self.game.server.State.player, all_banners())}
        self.assertLess(len(expected), len(all_banners()))
        for endpoint in ('GachaEntryRequest', 'GachaInfoRequest'):
            reply = self.exchange(endpoint, {})
            self.assertEqual({str(row['X1IuZnj2']) for row in reply['PcUrGH13']}, expected)
            self.assertTrue(reply['IC0ueV5s'])
            self.assertEqual({str(row['X1IuZnj2']) for row in reply['80nGg32w']}, expected)

    def test_season_and_collaboration_choices_cover_and_load_the_entire_catalogue(self):
        import importlib.util
        from ffbe_gacha import all_banners, gacha_groups, GACHA_MST_TAG
        from gacha_archive import catalogue, permanent
        spec = importlib.util.spec_from_file_location('android_archive_test',
            PROJECT / 'source/memorial/android/src/main/python/android_game.py')
        binding = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(binding)
        banners = all_banners()
        groups = catalogue(banners)
        self.assertEqual([g['label'] for g in groups],
                         ['Standard', 'Season 1', 'Season 2', 'Season 3', 'Season 4', 'Collab'])
        shared = {str(b['id']) for b in banners if permanent(b)}
        own = [bid for group in groups for bid in group['ids'] if bid not in shared]
        self.assertEqual(len(own), len(set(own)))
        # One entry per picture: a banner left out shares its art with a listed one.
        listed = set(own) | shared
        art = lambda b: str((b.get('art') or {}).get('banner') or '')
        listed_art = {art(b) for b in banners if str(b['id']) in listed}
        for b in banners:
            if str(b['id']) not in listed:
                self.assertIn(art(b), listed_art, b['id'])
        for group in groups:
            rows = gacha_groups([b for b in banners if str(b['id']) in group['ids']])[GACHA_MST_TAG]
            wire_types = {int(row['sx4kyW0i']) for row in rows}
            # Permanent summons are shared. Limited campaigns belong to their
            # dated season or collaboration, rather than the permanent group.
            self.assertTrue(wire_types - {0, 6, 900, 50, 7}, group['id'])
            self.assertTrue(wire_types & {0, 6, 900}, group['id'])
            if group['id'] != 'standard':
                self.assertTrue(wire_types & {50, 7, 5}, group['id'])
        before = copy.deepcopy(self.game.server.State.player.currencies)
        roster = copy.deepcopy(self.game.server.State.player.data['roster'])
        for group in groups:
            menu = json.loads(binding.summon_archive(self.game, group['id']))
            self.assertEqual(menu['selected']['id'], group['id'])
            self.assertEqual(menu['selected']['label'], group['label'])
            for endpoint in ('GachaEntryRequest', 'GachaInfoRequest'):
                reply = self.exchange(endpoint, {})
                self.assertEqual({r['X1IuZnj2'] for r in reply['PcUrGH13']}, set(group['ids']))
            self.game.server.State.player = self.restored_player()
            self.assertEqual(json.loads(binding.summon_archive(self.game))['selected']['id'], group['id'])
        self.assertEqual(self.game.server.State.player.currencies, before)
        self.assertEqual(self.game.server.State.player.data['roster'], roster)
        previous = self.restored_player().data['summon_archive']
        with self.assertRaises(ValueError):
            binding.summon_archive(self.game, 'missing')
        self.assertEqual(self.restored_player().data['summon_archive'], previous)

    def test_archive_uses_global_story_boundaries_and_recognizes_collaboration_art(self):
        from gacha_archive import catalogue, wire_type
        fixtures = [{'id': str(i + 9900000), 'name': 'Test', 'community': {'release': day}}
                    for i, day in enumerate(['2017-11-15', '2017-11-16', '2020-1-29',
                                             '2020-1-30', '2021-11-17', '2021-11-18'])]
        fixtures.append({'id': '9900099', 'name': 'Fencer, Juggler, Thief',
                         'art': {'banner': 'Gacha-Crystal Defenders.png'},
                         'community': {'release': '2016-08-01'}})
        fixtures.append({'id': '9900100', 'name': 'Friend', 'type': 'friend'})
        fixtures.append({'id': '9900101', 'name': 'Limited', 'type': 'limited',
                         'community': {'release': '2016-07-01'}})
        groups = catalogue(fixtures)
        assigned = {}
        for group in groups:
            for bid in group['ids']:
                assigned.setdefault(bid, set()).add(group['id'])
        self.assertEqual([assigned[str(i + 9900000)] for i in range(6)],
                         [{'season1'}, {'season2'}, {'season2'}, {'season3'}, {'season3'}, {'season4'}])
        self.assertEqual(assigned['9900099'], {'collaborations'})
        self.assertEqual(len(assigned['9900100']), 6)   # the friend summon is permanent
        self.assertEqual(wire_type(fixtures[0], 1), 50)  # an event banner -> Limited Time
        self.assertEqual(wire_type({'id': '1', 'type': 'normal', 'ticket_group_id': 5}, 1), 0)
        self.assertEqual(wire_type({'id': '2', 'type': 'normal', 'cost': {'kind': 'lapis'}}, 1), 1)

    def test_archive_groups_collaboration_series_in_native_schedule_order(self):
        from gacha_archive import visible_banners
        fixtures = [
            {'id': '9900200', 'name': 'NieR', 'release': '2021-11-18',
             'schedule': {'disp_order': 3000}},
            {'id': '9900201', 'name': 'Brave Frontier', 'release': '2017-05-12',
             'schedule': {'disp_order': 1000}},
            {'id': '9900202', 'name': 'Brave Frontier', 'release': '2016-11-11',
             'schedule': {'disp_order': 500}}]
        player = self.game.server.State.player
        player.data['summon_archive'] = 'collaborations'
        served = visible_banners(player, fixtures)
        native_order = sorted(served, key=lambda b: b['schedule']['disp_order'], reverse=True)
        self.assertEqual([b['id'] for b in native_order], ['9900202', '9900201', '9900200'])
        self.assertEqual(fixtures[0]['schedule']['disp_order'], 3000)

    def test_every_served_summon_image_loads_the_original_local_png(self):
        import struct
        from urllib.parse import quote
        from ffbe_gacha import (all_banners, banner_art_index, gacha_groups,
                                GACHA_SCHEDULE_TAG, GACHA_DETAIL_TAG)
        rows = gacha_groups(all_banners())
        requests = set()
        for schedule in rows[GACHA_SCHEDULE_TAG]:
            for entry in schedule['4yT7FUqj'].split(','):
                slot, name = ('sub', entry.split(':', 1)[1]) if ':' in entry else ('main', entry)
                requests.add((slot, name))
        for detail in rows[GACHA_DETAIL_TAG]:
            for entry in detail['4yT7FUqj'].split(','):
                if entry:
                    requests.add(('sub', entry.split(':', 1)[1]))
        self.assertGreater(len(requests), 800)
        index = banner_art_index()
        for slot, name in sorted(requests):
            with self.subTest(slot=slot, name=name):
                self.assertIn(name, index)
                response = self.game.request('GET', '/banner/en/sd/static_banner/gacha/' +
                                             slot + '/' + quote(name))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, Path(index[name]).read_bytes())
                self.assertEqual(response.body[:8], b'\x89PNG\r\n\x1a\n')
                width, height = struct.unpack('>II', response.body[16:24])
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)
                # The client CPK's rank-up placeholders (a flat navy box with the file name)
                # and its summon-screen overlays compress to under 0.08 bytes per pixel;
                # real banner art is above 0.29.
                self.assertGreater(len(response.body) / (width * height), 0.15)

    def test_existing_lapis_single_and_multi_banner_prices_and_awards(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 10000
        before = len(player.data['roster'])
        single = self.summon('11', '2011')
        self.assertEqual(len(single['5yLD4dYI'][0]['UJz5QED2'].split(',')), 1)
        self.assertEqual(player.currencies['lapis_free'], 9500)
        multi = self.summon('24', '24001', repeats=11)
        self.assertEqual(len(multi['5yLD4dYI'][0]['UJz5QED2'].split(',')), 11)
        self.assertEqual(player.currencies['lapis_free'], 4500)
        self.assertEqual(len(player.data['roster']), before + 12)
        restored = self.restored_player()
        self.assertEqual(restored.currencies['lapis_free'], 4500)
        self.assertEqual(len(restored.data['roster']), before + 12)

    def test_summoned_unit_can_join_existing_party_and_stay_favourited(self):
        player = self.game.server.State.player
        player.currencies['friend_point'] = 1000
        result = self.summon('1', '10011')
        instance_id = result['5yLD4dYI'][0]['UJz5QED2'].split(':')[2]
        deck = next(d for d in player.data['party']['decks']
                    if str(d['id']) == str(player.data['party']['active_deck']))
        self.exchange('PartyDeckEditRequest', {
            '5Eb0Rig6': [{'r21y0YzS': str(deck['id']), 'G4L0YIB2': 'Local party',
                          '2A6fYiEC': '0:0:' + instance_id}],
            'CN92arJK': [{'r21y0YzS': str(deck['id'])}]})
        favourite = self.exchange('UnitFavoriteRequest', {
            'R8U3uD1i': [{'9Eb7m1NR': instance_id}]})
        self.assertEqual(favourite['R8U3uD1i'][0]['9Eb7m1NR'], instance_id)
        self.assertEqual(self.restored_player().party_instance_ids(), [instance_id])
        self.assertEqual(self.restored_player().roster_row(instance_id)['favourite'], True)

    def test_existing_ticket_button_spends_ticket_instead_of_lapis(self):
        from player_state import ticket_by_id
        player = self.game.server.State.player
        kind, item_id, _ = ticket_by_id('12')
        player.grant_item(kind, item_id, 1)
        held = player.item_count(kind, item_id)
        player.currencies['lapis_free'] = 0
        before = len(player.data['roster'])
        result = self.summon('9100203', '91002031', ticket_id='12')
        self.assertEqual(result['5yLD4dYI'][0]['2RtVPS3b'], '12')
        self.assertEqual(player.item_count(kind, item_id), held - 1)
        self.assertEqual(player.currencies['lapis_free'], 0)
        self.assertEqual(len(player.data['roster']), before + 1)
        self.assertEqual(self.restored_player().item_count(kind, item_id), held - 1)

    def test_existing_step_up_continues_next_step_after_reload(self):
        from ffbe_gacha import all_banners
        banner = next(b for b in all_banners() if str(b['id']) == '150')
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 5000
        player.grant_item(20, 1209001041, 2)
        first = self.summon('150', '1501')
        self.assertTrue(first['5yLD4dYI'][0]['UJz5QED2'])
        self.assertEqual(player.data['gacha']['last_pull']['count'], 2)
        self.assertEqual(player.item_count(20, 1209001041), 1)
        self.assertEqual(player.currencies['lapis_free'], 5000)
        self.assertEqual(player.gacha_step(banner), 1)
        self.game.server.State.player = player = self.restored_player()
        second = self.summon('150', '1502')
        self.assertTrue(second['5yLD4dYI'][0]['UJz5QED2'])
        self.assertEqual(player.data['gacha']['last_pull']['count'], 3)
        self.assertEqual(player.item_count(20, 1209001041), 0)
        self.assertEqual(player.currencies['lapis_free'], 5000)
        self.assertEqual(self.restored_player().gacha_step(banner), 2)

    def test_named_step_up_keeps_native_type_and_refreshes_next_step(self):
        from ffbe_gacha import all_banners
        player = self.game.server.State.player
        player.data['summon_archive'] = 'season4'
        player.currencies['lapis_free'] = 10000
        entry = self.exchange('GachaEntryRequest', {})
        from ffbe_config import GACHA_MST_TAG, GACHA_DETAIL_TAG, GACHA_SCHEDULE_TAG
        self.assertEqual(next(r for r in entry['7k0FbQ8B'] if r['X1IuZnj2'] == '9200005')['upv38FtD'], '-1')
        row = next(r for r in entry[GACHA_MST_TAG] if r['X1IuZnj2'] == '9200005')
        self.assertEqual((row['sx4kyW0i'], row['7xBNR2MH']), ('5', '2'))
        initial_schedule = next(r for r in entry[GACHA_SCHEDULE_TAG] if r['X1IuZnj2'] == '9200005')
        self.assertIn('_06.png', initial_schedule['4yT7FUqj'])
        result = self.summon('9200005', '92000051')
        step_rows = {r['X1IuZnj2']: r['upv38FtD'] for r in result['7k0FbQ8B']}
        self.assertEqual(step_rows['9200005'], '0')
        details = [r for r in result[GACHA_DETAIL_TAG] if r['X1IuZnj2'] == '9200005']
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['nqzG3b2v'], '92000052')
        self.assertEqual(details[0]['0GgK6ytT'], '50:0:4000:1')
        self.assertIn('4000', details[0]['0GgK6ytT'])
        self.assertIn('_02.png', details[0]['4yT7FUqj'])
        schedule = next(r for r in result[GACHA_SCHEDULE_TAG] if r['X1IuZnj2'] == '9200005')
        self.assertIn('_02.png', schedule['4yT7FUqj'])
        self.assertIn('9200001', step_rows, 'step list is replaced by the native response reader')
        self.assertEqual(player.currencies['lapis_free'], 7000)
        self.assertEqual(len(result['5yLD4dYI'][0]['UJz5QED2'].split(',')), 7)
        self.assertEqual(player.data['gacha']['last_pull']['bonus_awards'], [{'kind': 10, 'id': 906000105, 'count': 1}])
        self.assertEqual(self.restored_player().gacha_step(next(b for b in all_banners()
                         if b['id'] == '9200005')), 1)

    def test_printed_multi_guarantee_applies_to_every_reserved_slot(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 3000
        with patch('player_state.random.random', return_value=0.999999):
            self.summon('9200005', '92000051')
        awards = player.data['gacha']['last_pull']['awards']
        self.assertEqual(len(awards), 7)
        self.assertTrue(all(int(a['granted_rarity']) >= 5 for a in awards[:6]))
        self.assertEqual(awards[6]['unit_id'], '906000105')
        self.assertEqual(player.currencies['lapis_free'], 0)

    def test_unfulfillable_guarantee_does_not_charge_or_advance(self):
        from ffbe_gacha import all_banners
        from player_state import expand_pool
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 5000
        banner = copy.deepcopy(next(b for b in all_banners() if b['id'] == '9200005'))
        banner['pool'] = [row for row in expand_pool(banner) if int(row['rarity']) < 7]
        player.data.setdefault('gacha', {}).setdefault('step', {})['9200005'] = 1
        self.assertEqual(banner['steps'][1]['guarantee'], {'rarity': 7, 'count': 2})
        before = copy.deepcopy(player.data)
        self.assertIsNone(player.roll_gacha(banner))
        self.assertEqual(player.currencies['lapis_free'], 5000)
        self.assertEqual(player.data['roster'], before['roster'])
        self.assertEqual(player.gacha_step(banner), 1)

    def test_local_nv_steps_work_and_keep_the_printed_slot_counts(self):
        from ffbe_gacha import all_banners
        from player_state import unit_mst, expand_pool
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 200000
        banners = [b for b in all_banners() if str(b['id']) in {str(i) for i in range(9200001, 9200007)}]
        self.assertEqual(len(banners), 6)
        for banner in banners:
            self.assertTrue(banner['pool_authored'])
            self.assertNotIn('Local rates:', banner['name'])
            self.assertIn('LOCAL RATES:', banner['rate_notice'])
            for step in banner['steps']:
                result = player.roll_gacha(banner)
                self.assertIsNotNone(result, banner['id'])
                guarantee = step['guarantee']
                reserved = sum(int(slot.get('count', 1)) for slot in step.get('guarantee_slots', []))
                end = int(step['draws']) - reserved
                awards = result['awards'][end-guarantee['count']:end]
                self.assertEqual(len(awards), guarantee['count'])
                self.assertTrue(all(int(unit_mst(a['unit_id'])['9fW0TePj']) >= guarantee['rarity'] for a in awards))
        lasswell = next(b for b in banners if b['id'] == '9200002')
        for index, chance in ((3, 0.02), (4, 0.025), (5, 0.05)):
            pool = expand_pool({'pool': lasswell['steps'][index]['guarantee']['pool']})
            self.assertAlmostEqual(sum(float(r['rate']) for r in pool if r['unit_id'] == '100044907') /
                                   sum(float(r['rate']) for r in pool), chance)

    def test_every_step_confirmation_charges_one_purchase_at_any_balance(self):
        from ffbe_gacha import all_banners, gacha_groups, GACHA_DETAIL_TAG
        player = self.game.server.State.player
        banners = [b for b in all_banners() if b.get('steps')]
        self.assertGreaterEqual(len(banners), 6)
        for banner in banners:
            for index, step in enumerate(banner['steps']):
                player.data.setdefault('gacha', {}).setdefault('step', {})[str(banner.get('state_id', banner['id']))] = index
                row = gacha_groups([banner])[GACHA_DETAIL_TAG][0]
                expected = int(step['cost'].get('amount', 0))
                if not expected:
                    self.assertEqual(row['0GgK6ytT'], '')
                    continue
                entries = row['0GgK6ytT'].split(',')
                self.assertEqual(len(entries), 1)
                kind, item, cost, count = map(int, entries[0].split(':'))
                self.assertEqual(count, 1, (banner['id'], index))
                self.assertEqual(cost, expected)
                if cost:
                    # GL9 initialize clamps exeCount to affordability, and
                    # setLayout multiplies the price by that count.
                    for held in (cost, cost * 2, cost * 10):
                        self.assertEqual(cost * min(count, held // cost), expected,
                                         (banner['id'], index, held))

    def test_unaffordable_existing_banner_does_not_charge_or_grant(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 499
        before = len(player.data['roster'])
        reply = self.summon('11', '2011')
        self.assertEqual(player.currencies['lapis_free'], 499)
        self.assertEqual(len(player.data['roster']), before)
        self.assertEqual(reply['5yLD4dYI'][0]['UJz5QED2'], '')
        self.assertEqual(reply['5yLD4dYI'][0]['oY0vAuE9'], '0')

    def test_unknown_banner_or_ticket_does_not_become_another_purchase(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 1000
        before = len(player.data['roster'])
        for banner, detail, ticket in (('999999999', '9999999991', '0'),
                                       ('9100203', '91002031', '999999999')):
            reply = self.summon(banner, detail, ticket_id=ticket)
            self.assertEqual(reply['5yLD4dYI'][0]['UJz5QED2'], '')
            self.assertEqual(player.currencies['lapis_free'], 1000)
            self.assertEqual(len(player.data['roster']), before)

    def test_real_stage_lapis_is_farmable_without_duplicate_completion_payment(self):
        player = self.game.server.State.player
        before = player.currencies['lapis_free']
        self.load_mission('1110101')
        self.finish_mission('1110101')
        self.assertEqual(player.currencies['lapis_free'], before + 50)
        first_progress = dict(player.data['quest_progress']['counters'])
        self.assertTrue(first_progress)
        self.finish_mission('1110101')
        self.assertEqual(player.currencies['lapis_free'], before + 50)
        self.assertEqual(player.data['quest_progress']['counters'], first_progress)
        self.game.server.State.player = player = self.restored_player()
        self.finish_mission('1110101')
        self.assertEqual(player.currencies['lapis_free'], before + 50)
        self.assertEqual(player.data['quest_progress']['counters'], first_progress)
        self.load_mission('1110101')
        replay = self.finish_mission('1110101')
        self.assertEqual(player.currencies['lapis_free'], before + 100)
        self.assertIn('0@50:1:50@0', replay['09HRWXDf'][0]['REB5tAL9'])
        self.assertNotIn('50:1:50', replay['09HRWXDf'][0].get('xF9Sr1a6', ''))
        self.assertEqual(self.restored_player().currencies['lapis_free'], before + 100)
        self.assertNotEqual(player.data['quest_progress']['counters'], first_progress)

    def test_recovered_exchange_shops_are_available_at_login(self):
        from exvius_actions_shops import archived_store_schedules
        reply = self.exchange('GetUserInfoRequest', {})
        expected = {row['Z20mNDvL'] for row in archived_store_schedules()}
        self.assertEqual(len(expected), 699)
        self.assertTrue(expected <= {row['Z20mNDvL'] for row in reply['3VS1Bhmf']})

    def test_recovered_exchange_unit_keeps_its_authored_level(self):
        player = self.game.server.State.player
        player.grant_item(20, '106213390', 1)
        before = len(player.data['roster'])
        request = {'2d6RAkvh': [{'Z20mNDvL': '7000152', 'L2gHC5ta': '200101:1'}]}
        self.exchange('MedalExchangeRequest', request)
        self.assertEqual(player.item_count(20, '106213390'), 0)
        self.assertEqual(len(player.data['roster']), before + 1)
        unit = player.data['roster'][-1]
        self.assertEqual(str(unit['master_id']), '207002007')
        self.assertEqual(unit['level'], 120)
        saved = copy.deepcopy(player.data)
        self.exchange('MedalExchangeRequest', request)
        self.assertEqual(player.data, saved)

    def test_native_fragment_and_permanent_shops_receive_products(self):
        reply = self.exchange('GachaSelectEntryRequest', {})
        self.assertEqual({r['JV8AIH3n'] for r in reply['F2rNo6qf']}, {'4', '5', '6'})
        self.assertGreater(len(reply['TPrh6Ay3']), 1500)
        self.assertTrue(all(r['uYcL8IQ1'] == '-1' for r in reply['F2rNo6qf']))
        self.assertNotIn('2147483647', {r['uYcL8IQ1'] for r in reply['TPrh6Ay3']})
        self.assertIn('20:293000100:1', {r['P4puB2ch'] for r in reply['TPrh6Ay3']})
        coin_shops = [r for r in reply['F2rNo6qf'] if r['JV8AIH3n'] == '6']
        self.assertEqual(len(coin_shops), 3)
        self.assertTrue(all(r['0GgK6ytT'] == '50:1' for r in coin_shops))
        self.assertTrue(all(r['0GgK6ytT'] != '50:1' for r in reply['F2rNo6qf']
                            if r['JV8AIH3n'] in ('4', '5')))

    def test_every_native_shop_offer_has_a_name_and_can_grant_its_reward(self):
        from exvius_shop_catalogue import catalogue, labels
        from exvius_actions_shops import _rewards, _grant
        player = self.game.server.State.player
        offers = catalogue()[2]
        self.assertEqual(set(offers), set(labels()))
        for pid, offer in offers.items():
            _rewards(offer['rewards'])
            for row in offer['rewards']:
                kind, iid, count = row['kind'], str(row['id']), row['count']
                if kind == 10:
                    before = len(player.data['roster'])
                    _grant([row])
                    self.assertEqual(len(player.data['roster']), before + count, pid)
                elif kind == 27:
                    before = len(player.data.get('vision_cards', []))
                    _grant([row])
                    self.assertEqual(len(player.data['vision_cards']), before + count, pid)
                elif kind == 60:
                    _grant([row])
                    self.assertTrue(player.data['exvius_craft']['books'][iid], pid)
                elif kind == 21:
                    owned = lambda: sum(int(r['Qy5EvcK1']) for r in player.equip_item_rows()
                                        if str(r['J1YX9kmM']) == iid)
                    before = owned()
                    _grant([row])
                    self.assertEqual(owned(), before + count, pid)
                else:
                    before = player.item_count(kind, iid)
                    _grant([row])
                    self.assertEqual(player.item_count(kind, iid), before + count, pid)

    def test_vip_shop_spends_lapis_and_persists_stock(self):
        player = self.game.server.State.player
        player.add_currency('lapis_free', 5000)
        player.grant_item(23, 110003, 1000)
        before = player.item_count(20, 293000100)
        self.exchange('GachaSelectExchangeExeRequest',
                      {'4mrD6JuA': [{'jPV7Xc4N': '940000009', 'Qy5EvcK1': '1'}]})
        self.assertEqual(player.currencies['lapis_free'], 4000)
        self.assertEqual(player.item_count(23, 110003), 1000)
        self.assertEqual(player.item_count(20, 293000100), before + 1)
        restored = self.restored_player()
        self.assertEqual(restored.item_count(20, 293000100), before + 1)
        self.assertEqual(restored.currencies['lapis_free'], 4000)
        self.game.server.State.player = player = restored
        self.exchange('GachaSelectExchangeExeRequest',
                      {'4mrD6JuA': [{'jPV7Xc4N': '940000009', 'Qy5EvcK1': '1'}]})
        self.assertEqual(player.currencies['lapis_free'], 3000)
        self.assertEqual(player.item_count(20, 293000100), before + 2)
        saved = copy.deepcopy(player.data)
        self.exchange('GachaSelectExchangeExeRequest',
                      {'4mrD6JuA': [{'jPV7Xc4N': '940000009', 'Qy5EvcK1': '1'}]})
        self.assertEqual(player.data, saved)

    def test_real_stage_other_challenge_rewards_stay_one_time(self):
        player = self.game.server.State.player
        before_lapis = player.currencies['lapis_free']
        before_item = player.item_count(20, '106211340')
        self.load_mission('8997903')
        self.finish_mission('8997903')
        self.assertEqual(player.currencies['lapis_free'], before_lapis + 100)
        self.assertEqual(player.item_count(20, '106211340'), before_item + 5)
        self.game.server.State.player = player = self.restored_player()
        self.load_mission('8997903')
        self.finish_mission('8997903')
        self.assertEqual(player.currencies['lapis_free'], before_lapis + 200)
        self.assertEqual(player.item_count(20, '106211340'), before_item + 5)

    def test_failed_stage_does_not_pay_farmable_lapis(self):
        player = self.game.server.State.player
        before = dict(player.currencies)
        before_progress = dict(player.data['quest_progress']['counters'])
        self.load_mission('1110101')
        self.finish_mission('1110101', cleared=False)
        self.assertNotIn('1110101', player.data['progress']['cleared_missions'])
        self.assertEqual(player.currencies['lapis_free'], before['lapis_free'])
        self.assertEqual(player.data['quest_progress']['counters'], before_progress)
        self.finish_mission('1110101')
        self.assertNotIn('1110101', player.data['progress']['cleared_missions'])
        self.assertEqual(player.currencies['lapis_free'], before['lapis_free'])
        self.assertEqual(player.data['quest_progress']['counters'], before_progress)

    def test_failed_esper_battle_cannot_unlock_esper_or_clear_switch_on_retry(self):
        from player_state import story_beast_for_mission
        mid = '1110404'
        beast = story_beast_for_mission(mid)
        self.assertIsNotNone(beast)
        player = self.game.server.State.player
        self.assertFalse(player.owns_beast(beast))
        self.load_mission(mid)
        switches = {kind: set(bits) for kind, bits in player.switches.items()}
        self.finish_mission(mid, cleared=False)
        self.finish_mission(mid, cleared=True)
        self.assertFalse(player.owns_beast(beast))
        self.assertNotIn(mid, player.data['progress']['cleared_missions'])
        self.assertEqual(player.switches, switches)
        self.load_mission(mid)
        self.finish_mission(mid, cleared=True)
        self.assertTrue(player.owns_beast(beast))
        self.assertIn(mid, self.restored_player().data['progress']['cleared_missions'])

    def test_noncombat_story_end_keeps_original_clear_without_battle_victory_log(self):
        from player_state import mission_wave_count
        mid = '9700101'
        self.assertEqual(mission_wave_count(mid), 0)
        self.exchange('MissionEndRequest', {'jQsE54Iz': [{'qo3PECw6': mid}]})
        self.assertIn(mid, self.restored_player().data['progress']['cleared_missions'])

    def test_clash_reward_pages_and_explicit_collection_persist_once(self):
        from exvius_fortuna import ensure, claim_token, policy
        player = self.game.server.State.player
        reward = next(r['reward'] for r in policy()['tiers']['1'] if r['reward'].startswith('20:'))
        kind, iid, count = map(int, reward.split(':'))
        feature = {'slots': reward + '-0', 'selection': True, 'pending': False, 'claimed': False}
        ensure(feature, '710001')
        player.data['exvius_tfa'] = feature
        before = player.item_count(kind, iid)
        page = self.game.request('GET', '/exvius/clash-rewards.html')
        self.assertEqual(page.status, 200)
        self.assertIn(b'Collect selected Fortuna rewards', page.body)
        self.assertEqual(page.body.count(b'<tr'), 100)
        ranking = self.game.request('GET', '/exvius/clash-ranking.html')
        self.assertEqual(ranking.status, 200)
        self.assertIn(b'Xenostone Shard', ranking.body)
        token = claim_token(player)
        self.game.request('HEAD', '/exvius/clash-rewards.html?claim=' + token)
        self.assertEqual(player.item_count(kind, iid), before)
        for _ in range(2):
            result = self.game.request('GET', '/exvius/clash-rewards.html?claim=' + token)
            self.assertEqual(result.status, 200)
            self.assertIn(b'Selected Fortuna rewards collected.', result.body)
        self.assertEqual(player.item_count(kind, iid), before + count)
        self.assertEqual(self.restored_player().item_count(kind, iid), before + count)

    def test_special_mode_clear_publishes_unlocks_in_the_same_reply(self):
        from event_archive import menu
        from ffbe_battle import _switch_container
        player = self.game.server.State.player
        menu(player, 'parade:92001')
        self.load_mission('9200101')
        reply = self.exchange('ParadeMissionEndRequest', {
            'jQsE54Iz': [{'qo3PECw6': '9200101'}],
            '2urzfX6d': [{'69ieJGhD': '0:123:2', 'Z1p0j9uF': '0'}]})
        switches = next(r['juA0Z4m7'] for r in reply['8J1R5PXG'] if r['5opcUT9t'] == '101')
        self.assertIn(4233, player.switches['101'])
        self.assertEqual(switches, _switch_container({}, '101'))
        self.assertIn('9200101', self.restored_player().data['progress']['cleared_missions'])

    def test_normal_battle_rewards_pay_once_per_load_and_survive_reload(self):
        mid = '1110101'
        report = {'jQsE54Iz': [{'qo3PECw6': mid}],
                  '2urzfX6d': [{'69ieJGhD': '1:1:3', 'Z1p0j9uF': '0'}],
                  'L4i4418y': [{'6q35TL07': '0'}],
                  '09HRWXDf': [{'Wdi3MAs2': '13', 'S4U09svH': '30'}]}
        player = self.game.server.State.player
        before_gil = player.currencies['gil']
        self.load_mission(mid)
        self.exchange('MissionEndRequest', report)
        self.assertEqual(player.currencies['gil'], before_gil + 13)
        saved = self.restored_player()
        self.game.server.State.player = player = saved
        rank, roster = json.loads(json.dumps(player.data['rank'])), json.loads(json.dumps(player.data['roster']))
        self.exchange('MissionEndRequest', report)
        self.assertEqual(player.currencies['gil'], before_gil + 13)
        self.assertEqual(player.data['rank'], rank)
        self.assertEqual(player.data['roster'], roster)
        self.load_mission(mid)
        self.exchange('MissionEndRequest', report)
        self.assertEqual(self.restored_player().currencies['gil'], before_gil + 26)

    def test_normal_reward_failure_rolls_back_and_leaves_attempt_unpaid(self):
        player = self.game.server.State.player
        self.load_mission('1110101')
        before_gil = player.currencies['gil']
        before = copy.deepcopy(player.data)
        report = {'jQsE54Iz': [{'qo3PECw6': '1110101'}],
                  '2urzfX6d': [{'69ieJGhD': '1:1:3'}],
                  '09HRWXDf': [{'Wdi3MAs2': '13', 'xF9Sr1a6': '20:106211340:2'}]}
        with patch.object(player, 'grant_item', side_effect=RuntimeError('grant failure')):
            with self.assertRaisesRegex(RuntimeError, 'grant failure'):
                self.exchange('MissionEndRequest', report)
        self.assertEqual(player.data, before)
        self.exchange('MissionEndRequest', report)
        self.assertEqual(self.restored_player().currencies['gil'], before_gil + 13)

    def test_original_king_mog_rewards_can_be_claimed_and_projected(self):
        from player_state import _load_ndjson
        event = json.loads((PROJECT / 'source/server/raid_rewards.json').read_text(encoding='utf-8'))['events'][0]
        player = self.game.server.State.player
        milestones = event['personal_milestones']
        self.assertEqual((len(milestones), milestones[-1]['points']), (55, 3750000))
        before_units = len(player.data['roster'])
        unit_rewards = 0
        for milestone in milestones:
            reward = milestone['reward']
            self.assertTrue(player._can_credit(reward), milestone['label'])
            mail = player.deliver_mail(milestone['label'], [(reward['kind'], reward['id'], reward['count'])])
            self.assertEqual(player.receive_mail(mail['mail_id']), [reward])
            self.assertEqual(player.receive_mail(mail['mail_id']), [])
            if reward['kind'] == 10:
                unit_rewards += reward['count']
        player.save(str(self.state_file), force=True)
        player = self.restored_player()
        self.assertEqual(len(player.data['roster']), before_units + unit_rewards)
        projected = player.apply_to_reply({'LhVz6aD2': []})
        self.assertEqual({r['H5jBL0Vf']: r['Qy5EvcK1'] for r in projected['rL81fVUI']},
                         {'504211130': '1', '504211140': '1'})
        bits = projected['ZrDPm3j5'][0]['eAM5B1qt']
        books = _load_ndjson('F_RECIPE_BOOK_MST.ndjson', 'staFu8U1')
        recipe_ids = [m['reward']['id'] for m in milestones if m['reward']['kind'] == 60]
        self.assertEqual(len(recipe_ids), 6)
        self.assertEqual(set(player.data['exvius_craft']['books']), set(map(str, recipe_ids)))
        expected = {int(books[str(iid)]['gJf3zp8a']) for iid in recipe_ids}
        actual = {n * 4 + bit for n, digit in enumerate(bits) for bit in range(4)
                  if int(digit, 16) & (8 >> bit)}
        self.assertEqual(actual, expected)

    def test_king_mog_counterattack_uses_global_boss_stats(self):
        reply = self.load_mission('7340105')
        boss = reply['bV34YIJQ'][0]
        self.assertEqual([boss[k] for k in ('xqartN26', 'G4L0YIB2', 'fh31sk7B', 'PC97pWQj',
                                          '9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')],
                         ['508001004', 'King Mog', '4000000', '10000', '630', '85', '600', '65'])
        self.assertEqual(boss['8a6gAwN9'], '508001001')
        self.assertEqual(boss['A5x02C6a'], '508001001')

    def test_original_raid_action_challenges_use_native_counts(self):
        from ffbe_battle import mission_result_from, CONDITION_CHECKS
        # Shape captured from the GL9 ELT clear after the original two skills.
        report = {'2urzfX6d': [{'Pqi5r1TZ': '501560:1,501580:1,1097010:1',
                               '69ieJGhD': '1:734010401:4', 'Z1p0j9uF': '0'}]}
        ctx = mission_result_from(json.dumps(report))
        self.assertTrue(CONDITION_CHECKS['21'](ctx, '501560'))
        self.assertFalse(CONDITION_CHECKS['21'](ctx, '501561'))
        self.load_mission('7340104')
        report['3uy7DzGB'] = [{'qo3PECw6': '7340104'}]
        self.exchange('MissionEndRequest', report)
        self.assertIn('73401042', self.restored_player().cleared_challenges['7340104'])
        for raw, expected in [('10020:1,20010:2', True), ('20010:2', False)]:
            ctx = mission_result_from(json.dumps({'2urzfX6d': [{'i1yJ3hmT': raw}]}))
            self.assertEqual(CONDITION_CHECKS['41'](ctx, '2'), expected)
            self.assertTrue(CONDITION_CHECKS['5'](ctx, ''))
            self.assertTrue(CONDITION_CHECKS['13'](ctx, '2'))
            self.assertEqual(CONDITION_CHECKS['13'](ctx, '1'), expected)
        ctx = mission_result_from(json.dumps({'2urzfX6d': [{'9JBtk2LE': '1:1',
                                                         '4p6CrcGt': '101003100:5'}]}))
        self.assertTrue(CONDITION_CHECKS['28'](ctx, ''))
        self.assertTrue(CONDITION_CHECKS['40'](ctx, '5'))
        self.assertFalse(CONDITION_CHECKS['40'](ctx, '4'))
        for report in ({}, {'2urzfX6d': [{'Pqi5r1TZ': '501560:-1'}]},
                       {'2urzfX6d': [{'Pqi5r1TZ': '501560:1,501560:1'}]}):
            self.assertIsNone(CONDITION_CHECKS['21'](mission_result_from(json.dumps(report)), '501560'))

    def test_raid_partial_damage_earns_points_coins_and_mail_once_even_on_a_loss(self):
        self.load_mission('7340105')
        reply = self.finish_mission('7340105', cleared=False, damage=1000000)
        player = self.restored_player()
        saved = player.data['exvius_raid_progress']['personal_events']['734']
        self.assertEqual(saved['points'], 2450)
        self.assertEqual(player.item_count(20, 106301500), 245)
        self.assertEqual(saved['mailed_milestones'], [300, 600, 2000])
        row = reply['09HRWXDf'][0]
        self.assertEqual(row['7a1Ugx4e'], '2450')
        self.assertIn('20:106301500:245', row['xF9Sr1a6'])
        before_mail = len(player.mailbox)
        self.finish_mission('7340105', cleared=False, damage=1000000)
        player = self.restored_player()
        self.assertEqual(player.item_count(20, 106301500), 245)
        self.assertEqual(len(player.mailbox), before_mail)
        menu = self.exchange('RoutineRaidMenuUpdateRequest', {'3uy7DzGB': [{'U9iHsau3': '73401'}]})
        self.assertEqual(menu['71ctQHWm'][0]['UbQ26oH4'], '2450')
        for method in ('GET', 'POST'):
            page = self.game.request(method, '/exvius/raid-rewards/73401.html', b'device=fixture',
                                     {'Content-Type': 'application/x-www-form-urlencoded'})
            self.assertEqual(page.status, 200)
            self.assertIn('text/html', page.headers['Content-Type'])
            self.assertEqual(page.body.count(b'<tr class='), 55)
            self.assertIn(b'2,450', page.body)
            self.assertIn(b'Mog Search', page.body)
            self.assertNotIn(b'<script', page.body)

    def test_king_mog_gate_uses_native_raid_state_and_the_original_event_banner(self):
        from ffbe_player import serve_event_gate
        retained = {'fSxqkF10': '42', 'VjJQ51uG': '2000-01-01 00:00:00',
                    'm8ivD4NX': '2099-01-01 00:00:00'}
        gate = serve_event_gate({'0xkoNP8U': [], 'jBL5XNf6': [retained]}, 'lEHBdOEf')
        row = next(r for r in gate['0xkoNP8U'] if r['uv60hgDW'] == '734')
        self.assertEqual((row['U9iHsau3'], row['qo3PECw6'], row['C8Qf5bs6']), ('73401', '7340101', '1'))
        self.assertEqual(row['4yT7FUqj'], 'Banner-One_Year_Celebration_Kupo.png')
        self.assertEqual({r['qo3PECw6'] for r in gate['0xkoNP8U'] if r['uv60hgDW'] == '734'},
                         {str(mid) for mid in range(7340101, 7340106)})
        self.assertIn(retained, gate['jBL5XNf6'])
        schedule = next(r for r in gate['jBL5XNf6'] if r['fSxqkF10'] == row['fSxqkF10'])
        self.assertEqual((schedule['VjJQ51uG'], schedule['m8ivD4NX']),
                         (row['VjJQ51uG'], row['m8ivD4NX']))
        image = self.game.request('GET', '/en/sd/area/Banner-One_Year_Celebration_Kupo.png')
        self.assertEqual(image.status, 200)
        self.assertTrue(image.body.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_event_header_art_is_filled_without_replacing_existing_backgrounds(self):
        from ffbe_player import serve_event_gate, event_gate_art
        original = {'uv60hgDW': '1046', 'A5efbo71': 'original-header.png'}
        missing = {'uv60hgDW': '1046', 'A5efbo71': ''}
        gate = serve_event_gate({'0xkoNP8U': [original, missing]}, 'lEHBdOEf')
        headers = [r['A5efbo71'] for r in gate['0xkoNP8U'] if r['uv60hgDW'] == '1046']
        self.assertIn('original-header.png', headers)
        self.assertIn(event_gate_art('1046'), headers)
        self.assertTrue(event_gate_art('1046'))

    def test_event_banners_use_distinct_original_art_and_load_offline(self):
        import hashlib
        from PIL import Image
        from ffbe_player import serve_event_gate
        art = json.loads((PROJECT / 'source/server/event_art.json').read_text(encoding='utf-8'))['events']
        gate = serve_event_gate({'0xkoNP8U': []}, 'lEHBdOEf')
        rows = {r['uv60hgDW']: r for r in gate['0xkoNP8U']}
        hashes = set()
        for area, entry in art.items():
            source = PROJECT / entry['source_file']
            runtime = PROJECT / entry['runtime_file']
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), entry['source_sha256'])
            self.assertEqual(hashlib.sha256(runtime.read_bytes()).hexdigest(), entry['runtime_sha256'])
            with Image.open(source) as original, Image.open(runtime) as converted:
                self.assertEqual(converted.size, original.size)
                self.assertEqual(original.convert('RGBA').tobytes(), converted.convert('RGBA').tobytes())
            self.assertEqual(rows[area]['4yT7FUqj'], entry['filename'])
            response = self.game.request('GET', '/en/sd/area/' + entry['filename'])
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, runtime.read_bytes())
            hashes.add(entry['runtime_sha256'])
        self.assertEqual(len(hashes), len({entry['source_sha256'] for entry in art.values()}))

    def test_solo_raid_level_bonus_does_not_scale_battle_hp_or_personal_thresholds(self):
        self.load_mission('7340105')
        self.finish_mission('7340105', damage=4000000)
        player = self.game.server.State.player
        saved = player.data['exvius_raid_progress']['personal_events']['734']
        saved['shared_damage'] = 40000000
        saved['points'] = 3745000
        event = json.loads((PROJECT / 'source/server/raid_rewards.json').read_text(encoding='utf-8'))['events'][0]
        saved['mailed_milestones'] = [m['points'] for m in event['personal_milestones'][:-1]]
        self.assertEqual(self.load_mission('7340105')['bV34YIJQ'][0]['fh31sk7B'], '4000000')
        reply = self.finish_mission('7340105', damage=8000000)
        self.assertEqual(reply['09HRWXDf'][0]['7a1Ugx4e'], '9800')
        self.assertEqual(reply['09HRWXDf'][0]['aK4k1PvY'], '1568')
        player = self.restored_player()
        saved = player.data['exvius_raid_progress']['personal_events']['734']
        self.assertEqual(saved['points'], 3756368)
        self.assertEqual(saved['shared_damage'], 44000000)
        self.assertEqual(saved['mailed_milestones'][-1], 3750000)
        self.assertEqual(player.mailbox[-1]['items'], [{'item_type': 10, 'item_id': 905000104, 'count': 1}])

    def test_raid_mail_failure_rolls_back_coins_points_and_partial_mail(self):
        from exvius_raid_progress import apply_personal_raid_result
        self.load_mission('7340105')
        player = self.game.server.State.player
        player.data['exvius_repeat']['attempt']['status'] = 'completed'
        report = json.dumps({'nSG9Jb1s': [{'NYb0Cri6': 'TOTAL_DAMAGE', '6gAX1BpC': '4000000'}]})
        before = copy.deepcopy(player.data)
        original = player.deliver_mail
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('mail fixture failure')
            return original(*args, **kwargs)
        with patch.object(player, 'deliver_mail', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'mail fixture failure'):
                apply_personal_raid_result(player, {'09HRWXDf': [{}]}, '7340105', report)
        self.assertEqual(player.data, before)

    def test_unsupported_recipe_mail_does_not_partly_credit(self):
        player = self.game.server.State.player
        before_gil = player.currencies['gil']
        mail = player.deliver_mail('Invalid recipe fixture', [(30, 1, 100), (60, 999999, 1)])
        self.assertEqual(player.receive_mail(mail['mail_id']), [])
        self.assertEqual(player.currencies['gil'], before_gil)
        self.assertEqual(mail['receive_type'], 0)

    def test_frozen_recipe_reward_does_not_change_ownership(self):
        player = self.game.server.State.player
        player.mode = 'frozen'
        before = copy.deepcopy(player.data)
        self.assertEqual(player._grant_items([{'kind': 60, 'id': 905211120, 'count': 1}]), [])
        self.assertEqual(player.data, before)

    def test_actual_raid_mission_records_local_completion_once_when_explicitly_configured(self):
        # The mission/battle data is real. The temporary pacing value is a
        # synthetic test setting, not a recovered historical shared raid goal.
        mid = '7340105'
        path = self.root / 'state/exvius_raids.json'
        config = {'version': 1, 'events': [{'event_id': '734', 'mission_ids': [mid],
                  'source': 'Synthetic pacing fixture for an existing raid mission',
                  'original_shared_goal': 1000, 'target_solo_clears': 10, 'shared_milestones': []}]}
        path.write_text(json.dumps(config), encoding='utf-8')
        self.addCleanup(path.unlink, missing_ok=True)
        player = self.game.server.State.player
        self.load_mission(mid)
        self.finish_mission(mid, cleared=False)
        self.assertNotIn('exvius_raid_progress', player.data)
        self.load_mission(mid)
        self.finish_mission(mid)
        self.assertEqual(self.restored_player().data['exvius_raid_progress']['events']['734']['clears'], 1)
        self.game.server.State.player = player = self.restored_player()
        self.finish_mission(mid)
        self.assertEqual(player.data['exvius_raid_progress']['events']['734']['clears'], 1)
        self.load_mission(mid)
        self.finish_mission(mid)
        self.assertEqual(self.restored_player().data['exvius_raid_progress']['events']['734']['clears'], 2)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), config)

    def test_missing_event_encounters_never_load_the_default_battle_or_pay_rewards(self):
        player = self.game.server.State.player
        before = copy.deepcopy(player.data)
        with patch.dict(self.game.server.State.replies), \
                patch('battle_content.event_encounter', return_value=None), \
                patch('battle_content.event_binding', return_value=None):
            for mid in ('9700104', '9700106', '9700108', '9700110', '9700111', '9700112'):
                self.game.server.State.replies.pop('jnw49dUq@' + mid, None)
                with self.subTest(mission=mid):
                    before_load = copy.deepcopy(player.data)
                    response = self.load_mission(mid, expected_status=404)
                    self.assertEqual(response.body, b'')
                    self.assertEqual(player.data, before_load)
                    self.finish_mission(mid)
                    self.assertEqual(player.currencies, before['currencies'])
                    self.assertNotIn(mid, player.data['progress']['cleared_missions'])
                    self.assertNotIn('exvius_repeat', player.data)

    def test_reconstructed_morgana_lgd_uses_global_stats_ai_skills_and_amethyst(self):
        reply = self.load_mission('9700112')
        self.assertEqual({r['qo3PECw6'] for r in reply['an6TB4WS']}, {'9700112'})
        self.assertEqual({r['xqartN26'] for r in reply['Bi6hVv34']}, {'900010677'})
        part = reply['bV34YIJQ'][0]
        self.assertEqual((part['fh31sk7B'], part['PC97pWQj']), ('10000000', '100000'))
        self.assertEqual((part['9NBV1XCS'], part['Pn5w9dfh'], part['84FJM3PD'], part['T8xMDAZ4']),
                         ('400', '100', '500', '300'))
        self.assertEqual((part['8a6gAwN9'], part['A5x02C6a'], part['4Y2DGP7m']),
                         ('900010671', '900010671', '10,10'))
        skills = {r['6E5u1xrs']: r for r in reply['Wp39QX52']}
        self.assertEqual(set(skills), {'900305', '900306', '900307', '900308', '900309'})
        self.assertEqual(skills['900307']['Ha9G5sCS'], '0,0,0,0,0,350@20000')
        self.assertEqual(skills['900307']['a4hXTIm0'], '1@3')
        drops = ','.join(r['9BetM2Ds'] for r in reply['y35YvQjZ'])
        self.assertIn('20:1209000976:450:100', drops)
        self.assertIn('20:1209000975:1200:100', drops)
        self.assertNotIn('310001240', drops)
        self.assertEqual(self.restored_player().data['exvius_repeat']['attempt']['mid'], '9700112')

    def test_zero_wave_field_keeps_original_groups_without_default_battle(self):
        # No automatic battle waves. The map's original encounter group must
        # still be present for a battle triggered by a field event.
        from player_state import mission_row
        player = self.game.server.State.player
        self.load_mission('1002001')  # first reply also sets the base switches
        before = copy.deepcopy(player.data)
        with patch.dict(self.game.server.State.replies):
            self.game.server.State.replies.pop('jnw49dUq@9700101', None)
            reply = self.load_mission('9700101')
        self.assertEqual({row['6uIYE15X'] for row in reply['1IfDqR4n']}, {'9700101'})
        self.assertEqual([(row['gou39JeI'], row['6uIYE15X']) for row in reply['an6TB4WS']],
                         [('1', '9002727')])
        self.assertEqual(reply.get('y35YvQjZ', []), [])
        self.assertEqual({r['2fY1IomW'] for r in reply['Bi6hVv34']}, {'970010101'})
        self.assertEqual({r['xqartN26'] for r in reply['bV34YIJQ']}, {'308161005'})
        # Loading a mission opens its attempt; nothing else in the save changes.
        after = copy.deepcopy(player.data)
        self.assertEqual(after.pop('exvius_repeat')['attempt']['mid'], '9700101')
        before.pop('exvius_repeat', None)
        self.assertEqual(after, before)

    def test_story_movie_missions_keep_the_original_scene_entry_phases(self):
        for mid, event in [('4021804', '4018003'), ('32820208', '4023009')]:
            with self.subTest(mission=mid):
                reply = self.load_mission(mid)
                self.assertEqual([(r['gou39JeI'], r['6uIYE15X'])
                                  for r in reply['an6TB4WS']], [('1', event)])
                self.assertEqual({r['6uIYE15X'] for r in reply['1IfDqR4n']}, {mid})
                self.assertNotIn(mid, self.restored_player().data['progress']['cleared_missions'])

    def test_story_completion_without_combat_log_grants_global_progress_once(self):
        from player_state import switch_position
        mid = '32820208'
        self.load_mission(mid)
        report = {'jQsE54Iz': [{'qo3PECw6': mid}]}
        self.exchange('MissionEndRequest', report)
        player = self.restored_player()
        self.assertIn(mid, player.data['progress']['cleared_missions'])
        stype, bit = switch_position('1083')
        self.assertIn(bit, player.switches[stype])
        attempt = player.data['exvius_repeat']['attempt']
        self.assertTrue(attempt['cleared'])
        self.assertTrue(attempt['quest_progress_recorded'])
        before = copy.deepcopy(player.data)
        self.exchange('MissionEndRequest', report)
        self.assertEqual(self.restored_player().data, before)

    def test_story_resource_progress_keeps_the_two_scene_parts_separate(self):
        reply = self.load_mission('4021804')
        parts = {}
        for row in reply['1IfDqR4n']:
            parts.setdefault(row['0G7J2vfD'], set()).add(row['pJ56sAEo'])
        self.assertIn('402220100.cpk', parts['0'])
        self.assertIn('402220105.cpk', parts['0'])
        self.assertNotIn('402220156.cpk', parts['0'])
        self.assertIn('402220150.cpk', parts['1'])
        self.assertIn('402220156.cpk', parts['1'])
        self.assertNotIn('402220105.cpk', parts['1'])

    def test_global_story_scenes_have_playable_entry_phases(self):
        for mid, scene, filename in [('9700101', '9002727', '90001001.cpk'),
                                      ('10480101', '10480101', '90001301.cpk'),
                                      ('99550101', '99550101', '5002000101.cpk')]:
            with self.subTest(mission=mid):
                reply = self.load_mission(mid)
                self.assertEqual([(r['gou39JeI'], r['6uIYE15X'])
                                  for r in reply['an6TB4WS']], [('1', scene)])
                self.assertIn(filename, {r['pJ56sAEo'] for r in reply['1IfDqR4n']})
                self.assertNotIn(mid, self.restored_player().data['progress']['cleared_missions'])

    def test_equipment_enhancement_notice_loads_without_changing_the_save(self):
        before = copy.deepcopy(self.game.server.State.player.data)
        for method in ('GET', 'HEAD'):
            response = self.game.request(method, '/exvius/equipment-enhancement.html')
            self.assertEqual(response.status, 200)
            self.assertIn('text/html', response.headers['Content-Type'])
            if method == 'GET':
                self.assertIn(b'Select Equipment to Enhance', response.body)
        self.assertEqual(self.game.server.State.player.data, before)

    def test_native_parade_completion_webview_lists_original_rewards(self):
        from event_archive import menu
        menu(self.game.server.State.player, 'parade:92001')
        response = self.game.request('GET', '/exvius/parade-rewards.html')
        self.assertEqual(response.status, 200)
        text = response.body.decode('utf-8')
        self.assertIn('Completion Rewards', text)
        self.assertIn('Dark Matter', text)
        self.assertIn('25,000', text)

    def test_four_wave_original_event_cannot_load_single_wave_memorial_replacement(self):
        before = copy.deepcopy(self.game.server.State.player.data)
        with patch.dict(self.game.server.State.replies), \
                patch('battle_content.event_encounter', return_value=None), \
                patch('battle_content.event_binding', return_value=None):
            self.game.server.State.replies.pop('jnw49dUq@9700102', None)
            response = self.load_mission('9700102', expected_status=404)
        self.assertEqual(response.body, b'')
        self.assertEqual(self.game.server.State.player.data, before)

    def test_followers_restores_recorded_groups_and_original_sprite_ids(self):
        reply = self.load_mission('9700102')
        phases = reply['an6TB4WS']
        self.assertEqual(len(phases), 4)
        profiles = {r['xqartN26']: r for r in reply['bV34YIJQ']}
        monsters = {r['xqartN26']: r for r in reply['wbet57nF']}
        total_xp = 0
        for wave, count in zip(phases, (1, 2, 3, 1)):
            slots = [g for g in reply['Bi6hVv34'] if g['2fY1IomW'] == wave['2fY1IomW']]
            self.assertEqual(len(slots), count)
            captain = wave['6v7y3QcJ'] == '4'
            for slot in slots:
                pid = slot['xqartN26']
                self.assertEqual(monsters[pid]['V9j8wJcC'], '10000049' if captain else '10000053')
                self.assertEqual(profiles[pid]['fh31sk7B'], '200000' if captain else '100000')
                total_xp += int(profiles[pid]['B6H34Mea'])
        self.assertEqual(total_xp, 1750)
        self.assertNotIn('Ifrit', str(reply['wbet57nF']))

    def test_event_cutscenes_preserve_original_global_script_resources(self):
        for mid, script in (('9700101', '90001001'), ('9700103', '90001002'),
                            ('9700105', '90001003'), ('9700107', '90001004'),
                            ('9700109', '90001005')):
            with self.subTest(mission=mid):
                reply = self.load_mission(mid)
                self.assertEqual(reply['1IfDqR4n'][0]['qo3PECw6'], mid)
                self.assertIn(script, reply['1IfDqR4n'][0]['q4f9IdMs'].split(','))
                self.assertFalse(reply.get('Bi6hVv34'))
                self.assertFalse(reply.get('an6TB4WS'))

    def test_authored_bundle_cannot_serve_another_missions_phases(self):
        state = self.game.server.State
        key = 'jnw49dUq@9700104'
        before = copy.deepcopy(state.player.data)
        with patch.dict(state.replies, {key: copy.deepcopy(state.replies['jnw49dUq'])}):
            response = self.load_mission('9700104', expected_status=404)
        self.assertEqual(response.body, b'')
        self.assertEqual(state.player.data, before)

    def test_disabling_derivation_cannot_reenable_default_battle_fallback(self):
        with patch.dict(self.game.server.State.replies), patch.dict(os.environ, {'BATTLE_DERIVE': 'off'}):
            self.game.server.State.replies.pop('jnw49dUq@9700111', None)
            response = self.load_mission('9700111', expected_status=404)
        self.assertEqual(response.body, b'')

    def test_reconstructed_event_lineups_resolve_every_wave_skill_and_drop(self):
        seen = set()
        expected = {'9700104': (['Fossil Dragon', 'Leanan-Sidhe', 'Gargoyle'], 1200),
                    '9700106': (['Evil Drake'], 150), '9700108': (['Morgana'], 1000),
                    '9700110': (['Morgana'], 2000), '9700111': (['Morgana'], 5000)}
        for mid, (names, experience) in expected.items():
            with self.subTest(mission=mid):
                reply = self.load_mission(mid)
                phases = reply['an6TB4WS']
                self.assertEqual(len(phases), len(names))
                self.assertEqual({p['qo3PECw6'] for p in phases}, {mid})
                groups = {r['2fY1IomW']: r for r in reply['Bi6hVv34']}
                monsters = {r['xqartN26']: r for r in reply['wbet57nF']}
                lineup = [monsters[groups[p['2fY1IomW']]['xqartN26']]['G4L0YIB2'] for p in phases]
                self.assertEqual(lineup, names)
                ids = {r['xqartN26'] for r in reply['bV34YIJQ']}
                self.assertFalse(ids & seen)
                seen.update(ids)
                self.assertTrue(all(int(i) < 2147483648 for i in ids))
                self.assertEqual(sum(int(r['B6H34Mea']) for r in reply['bV34YIJQ']), experience)
                self.assertTrue(reply['Wp39QX52'])
                self.assertEqual(len(reply['y35YvQjZ']), len(names))
                for row in reply['y35YvQjZ']:
                    self.assertNotIn('310001240', row['9BetM2Ds'])
                    self.assertTrue(all(len(e.split(':')) == 4 for e in row['9BetM2Ds'].split(',')))

    def test_story_map_events_load_without_a_battle_or_save_change(self):
        # Entering Latius Woods after Earth Shrine requests map event 1002001
        # through the battle-bundle carrier; it used to return an empty 404.
        from player_state import _load_ndjson, mission_wave_count
        events = {row['4SWuwc0M'] for row in _load_ndjson('F_MAP_EVENT_MST.ndjson')['__rows__']}
        self.assertIn('1002001', events)
        player = self.game.server.State.player
        self.load_mission('1002001')  # first reply also sets the base switches
        for mid in sorted(events):
            if mission_wave_count(mid) is not None or ('jnw49dUq@' + mid) in self.game.server.State.replies:
                continue  # also a mission id; covered by the mission tests
            with self.subTest(map_event=mid):
                before = copy.deepcopy(player.data)
                reply = self.load_mission(mid)
                for group in ('1IfDqR4n', 'an6TB4WS', 'Bi6hVv34', 'bV34YIJQ', 'wbet57nF', 'y35YvQjZ', 'Wp39QX52'):
                    self.assertEqual(reply.get(group, []), [], group)
                self.assertEqual(player.data, before)

    def test_event_header_resource_has_no_cost_attempt_or_progress_side_effect(self):
        from player_state import mission_row
        self.load_mission('1002001')
        player = self.game.server.State.player
        before = copy.deepcopy(player.data)
        reply = self.load_mission('51210001')
        self.assertEqual(reply['1IfDqR4n'], [mission_row('51210001')])
        for group in ('an6TB4WS', 'Bi6hVv34', 'bV34YIJQ', 'wbet57nF', 'Wp39QX52'):
            self.assertFalse(reply.get(group))
        self.assertEqual(player.data, before)

    def test_event_exploration_keeps_original_scripts_without_inventing_opening_enemies(self):
        from player_state import mission_row
        mid = '4021015'
        reply = self.load_mission(mid)
        self.assertEqual(reply['1IfDqR4n'], [mission_row(mid)])
        self.assertIn('294025', reply['1IfDqR4n'][0]['q4f9IdMs'].split(','))
        for group in ('an6TB4WS', 'Bi6hVv34', 'bV34YIJQ', 'wbet57nF', 'Wp39QX52'):
            self.assertFalse(reply.get(group))
        self.assertEqual(self.restored_player().data['exvius_repeat']['attempt']['mid'], mid)

    def test_towns_load_without_a_battle_or_save_change(self):
        # Entering Town of Mitra requests its town id (1101) through the
        # battle-bundle carrier; it used to return an empty 404.
        from player_state import _load_ndjson
        towns = sorted(_load_ndjson('F_TOWN_MST.ndjson', 'Gh92V3Tx'))
        self.assertIn('1101', towns)
        player = self.game.server.State.player
        self.load_mission('1101')  # first reply also sets the base switches
        for town in towns:
            with self.subTest(town=town):
                before = copy.deepcopy(player.data)
                reply = self.load_mission(town)
                for group in ('1IfDqR4n', 'an6TB4WS', 'Bi6hVv34', 'bV34YIJQ', 'wbet57nF', 'y35YvQjZ', 'Wp39QX52'):
                    self.assertEqual(reply.get(group, []), [], group)
                self.assertEqual(player.data, before)

    def test_missing_mission_id_cannot_load_default_battle(self):
        before = copy.deepcopy(self.game.server.State.player.data)
        response = self.exchange('DungeonResourceLoadMstListRequest', {}, expected_status=404)
        self.assertEqual(response.body, b'')
        self.assertEqual(self.game.server.State.player.data, before)

    def test_home_rotation_is_disabled_and_clears_stale_banner_rows(self):
        from ffbe_banner import serve_home_marquee, MARQUEE_FLAG
        self.assertEqual(MARQUEE_FLAG, '0')
        source={'DxCN9SNZ':[{'nZfbucEw':'13630'}], 'PJm9d197':[{'P_GS_FEATURE_HOME_MARQUEE':'1'}]}
        out=serve_home_marquee(source, 'fixture')
        self.assertEqual(out['DxCN9SNZ'], [])
        self.assertEqual(out['PJm9d197'][0]['P_GS_FEATURE_HOME_MARQUEE'], '0')
        self.assertEqual(source['PJm9d197'][0]['P_GS_FEATURE_HOME_MARQUEE'], '1')

    def test_event_menu_uses_saved_local_selection_and_local_clock(self):
        from exvius_events import save_policy
        policy_file = self.root / 'state/exvius_events.json'
        self.addCleanup(policy_file.unlink, missing_ok=True)
        save_policy(self.root, {'version': 1, 'areas': [970], 'permanent': True})
        for endpoint in ('GetBackgroundDownloadInfoRequest', 'RoutineWorldUpdateRequest'):
            with patch('exvius_events.time.time', return_value=2300000000):
                reply = self.exchange(endpoint, {})
            rows = reply['0xkoNP8U']
            selected = [r for r in rows if str(r['uv60hgDW']) == '970']
            from player_state import _load_ndjson
            missions = {r['qo3PECw6'] for r in _load_ndjson('F_MISSION_MST.ndjson')['__rows__'] if r.get('uv60hgDW') == '970'}
            self.assertEqual({r['qo3PECw6'] for r in selected}, missions)
            first = next(r for r in selected if r['qo3PECw6'] == '9700101')
            self.assertEqual(first['U9iHsau3'], '97001')
            for row in selected:
                self.assertLess(calendar.timegm(time.strptime(row['VjJQ51uG'], '%Y-%m-%d %H:%M:%S')), 2300000000)
                self.assertGreater(calendar.timegm(time.strptime(row['m8ivD4NX'], '%Y-%m-%d %H:%M:%S')), 2300000000)
            self.assertNotIn('888', {str(r['uv60hgDW']) for r in rows})
        save_policy(self.root, {'version': 1, 'areas': [888], 'permanent': True})
        from local_game import LocalGame
        reopened = LocalGame(self.root, slot='localtest')
        self.assertIs(reopened.server, self.game.server)
        reply = self.exchange('RoutineWorldUpdateRequest', {})
        areas = {str(r['uv60hgDW']) for r in reply['0xkoNP8U']}
        self.assertIn('888', areas)
        self.assertNotIn('970', areas)

    def test_login_reply_delivers_the_bundle_offers(self):
        # The Bundles screen sends no request; it lists the BundleMst rows an earlier reply carried.
        reply = self.exchange('GetUserInfoRequest', {})
        offer = next(row for row in reply['fMohhKK8'] if row['EzXXHtTY'] == '990000001')
        self.assertEqual((offer['pRYHbNN5'], offer['AOHRcCC2']), ('50', '100'))
        self.assertGreaterEqual(int(offer['gzWIBU0I']), 1)  # BundleInfo::canPurchase needs a limit >= 1
        self.assertRegex(offer['m8ivD4NX'], r'^\d{4}-\d\d-\d\d ')  # end date is parsed as date text
        self.assertIn('LhVz6aD2', reply)

    def test_global_bundles_are_priced_limited_and_bought(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'], player.currencies['gil'] = 500, 50000
        offers = {row['EzXXHtTY']: row for row in self.exchange('GetUserInfoRequest', {})['fMohhKK8']}
        self.assertEqual((offers['990000101']['pRYHbNN5'], offers['990000101']['AOHRcCC2']), ('50', '242'))
        self.assertEqual(offers['990000103']['pRYHbNN5'], '30')  # gil price kept
        reply = self.exchange('BundlePurchaseRequest', {'blmGz1EI': [{'EzXXHtTY': '990000105'}]})
        self.assertEqual(player.currencies['lapis_free'], 400)
        self.assertEqual(player.currencies['gil'], 1050000)
        self.assertNotIn('990000105', {row['EzXXHtTY'] for row in reply['fMohhKK8']})  # once per day
        self.exchange('BundlePurchaseRequest', {'blmGz1EI': [{'EzXXHtTY': '990000103'}]})
        self.assertEqual(player.currencies['gil'], 1030000)
        self.assertEqual(self.restored_player().data['bundle_purchases']['990000103']['count'], 1)

    def test_friend_point_shop_uses_existing_bundle_purchase_and_save(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 500
        before_fp = player.currencies['friend_point']
        catalogue = self.exchange('BundleStatusRequest', {})
        offer = next(row for row in catalogue['fMohhKK8'] if row['EzXXHtTY'] == '990000001')
        self.assertEqual(offer['pRYHbNN5'], '50')
        self.assertEqual(offer['AOHRcCC2'], '100')
        self.exchange('BundlePurchaseRequest', {'blmGz1EI': [{'EzXXHtTY': '990000001'}]})
        self.assertEqual(player.currencies['lapis_free'], 400)
        self.assertEqual(player.currencies['friend_point'], before_fp + 2000)
        restored = self.restored_player()
        self.assertEqual(restored.currencies['lapis_free'], 400)
        self.assertEqual(restored.currencies['friend_point'], before_fp + 2000)
        self.game.server.State.player = restored
        before_roster = len(restored.data['roster'])
        self.summon('1', '10011')
        self.assertEqual(restored.currencies['lapis_free'], 400)
        self.assertEqual(restored.currencies['friend_point'], before_fp + 1800)
        self.assertEqual(len(self.restored_player().data['roster']), before_roster + 1)

    def test_cash_bundle_price_changes_to_lapis_and_contents_are_retained(self):
        state = self.game.server.State
        original = {
            'fMohhKK8': [{'EzXXHtTY': 'fixture-cash', 'pRYHbNN5': '9999',
                          'AOHRcCC2': '0.99', 'TzvJwA60': 'fixture.product'}],
            'pcjqhOI8': [{'EzXXHtTY': 'fixture-cash', '4FF0gz8P': '1',
                         'jsvoa0I2': '51:1:3000'}],
        }
        state.replies['fixture-shop'] = original
        self.addCleanup(state.replies.pop, 'fixture-shop', None)
        player = state.player
        player.currencies['lapis_free'] = 500
        before_fp = player.currencies['friend_point']
        catalogue = self.exchange('BundleStatusRequest', {})
        offer = next(row for row in catalogue['fMohhKK8'] if row['EzXXHtTY'] == 'fixture-cash')
        self.assertEqual((offer['pRYHbNN5'], offer['AOHRcCC2'], offer['TzvJwA60']), ('50', '120', ''))
        self.assertEqual(catalogue['pcjqhOI8'][0], original['pcjqhOI8'][0])
        self.assertEqual(original['fMohhKK8'][0]['pRYHbNN5'], '9999')
        self.exchange('BundlePurchaseRequest', {'blmGz1EI': [{'EzXXHtTY': 'fixture-cash'}]})
        self.assertEqual(player.currencies['lapis_free'], 380)
        self.assertEqual(player.currencies['friend_point'], before_fp + 3000)

    def test_friend_point_purchase_cannot_overdraw_lapis(self):
        player = self.game.server.State.player
        player.currencies['lapis_free'] = 99
        player.currencies['lapis_paid'] = 0
        before_fp = player.currencies['friend_point']
        with self.assertRaisesRegex(ValueError, 'Not enough Lapis'):
            self.exchange('BundlePurchaseRequest', {'blmGz1EI': [{'EzXXHtTY': '990000001'}]})
        self.assertEqual(player.currencies['lapis_free'], 99)
        self.assertEqual(player.currencies['friend_point'], before_fp)

    def test_daily_signin_keeps_original_reward_and_cannot_repeat_after_deletion(self):
        from ffbe_player import _login_bonus_month, login_calendar
        player = self.game.server.State.player
        reply = self.daily_login('2026-10-29')
        self.assertEqual(player.data['login_bonus']['day'], 1)
        reward = login_calendar()[_login_bonus_month()[0]]['days']['1']
        first = reply['f5bA4wFx'][0]
        self.assertEqual((int(first['YWF08vZS']), int(first['tL6G9egd']), int(first['5GNDIwPX'])),
                         (int(reward['type']), int(reward['id']), int(reward['count'])))
        self.assertEqual(len(self.daily_mails()), 1)
        mail_id = self.daily_mails()[0]['mail_id']
        self.exchange('MailReceiptRequest', {'rStH7od8': [{
            'gSEN0jb7': '1', 'Qe02W7rX': mail_id + ':2'}]})
        self.assertEqual(self.daily_mails()[0]['receive_type'], 2)
        after = dict(player.currencies)
        self.exchange('MailReceiptRequest', {'rStH7od8': [{
            'gSEN0jb7': '3', 'Qe02W7rX': mail_id + ':2'}]})
        self.assertEqual(self.daily_mails(), [])
        self.game.server.State.player = player = self.restored_player()
        self.daily_login('2026-10-29')
        self.assertEqual(player.data['login_bonus']['day'], 1)
        self.assertEqual(self.daily_mails(), [])
        self.assertEqual(player.currencies, after)

    def test_daily_signin_only_advances_once_per_played_day_and_resets_next_month(self):
        player = self.game.server.State.player
        self.daily_login('2026-10-29')
        first_id = self.daily_mails()[0]['mail_id']
        self.daily_login('2026-10-29')
        self.assertEqual(player.data['login_bonus']['day'], 1)
        self.assertEqual(len(self.daily_mails()), 1)
        self.game.server.State.player = player = self.restored_player()
        self.daily_login('2026-10-31')
        self.assertEqual(player.data['login_bonus']['day'], 2)
        self.assertEqual(len(self.daily_mails()), 2)
        self.daily_login('2026-11-01')
        self.assertEqual(player.data['login_bonus']['day'], 1)
        self.assertEqual(len(self.daily_mails()), 3)
        self.assertNotEqual(self.daily_mails()[-1]['mail_id'], first_id)
        self.assertEqual(self.restored_player().data['login_bonus']['issued_rewards'],
                         {'2026-10': 2, '2026-11': 1})

    def test_existing_daily_save_does_not_receive_its_current_day_again(self):
        from ffbe_player import _login_bonus_month
        player = self.game.server.State.player
        player.data['login_bonus'] = {
            'month': _login_bonus_month()[0], 'day': 5, 'last_advance': '2026-10-29'}
        before = dict(player.currencies)
        self.daily_login('2026-10-29')
        self.assertEqual(player.data['login_bonus']['day'], 5)
        self.assertEqual(player.currencies, before)
        self.assertEqual(self.daily_mails(), [])
        self.game.server.State.player = player = self.restored_player()
        self.daily_login('2026-10-30')
        self.assertEqual(player.data['login_bonus']['day'], 6)
        self.assertEqual(len(self.daily_mails()), 1)
        self.assertEqual(self.daily_mails()[0]['message'], '6')


if __name__ == '__main__':
    unittest.main()
