import raidArchive from '../server/raid_archive.json';
import anniversaryRaid from '../server/raid_rewards.json';

// Keep the original raid screen and WebView. Its personal rewards come from local data.
export function installRaidMenu(module, note, retained, bridge) {
  const fn = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const rewardIds = new Map();
  for (const event of [...anniversaryRaid.events, ...raidArchive.events])
    for (const id of [event.dungeon_id, ...(event.dungeon_ids || [])])
      rewardIds.set(Number(id), Number(event.reward_banner_id));
  const headerRaids = [];
  const makeArray = fn('_ZN7cocos2d7__Array6createEv', 'pointer', []);
  const append = fn('_ZN7cocos2d7__Array9addObjectEPNS_3RefE', 'void', ['pointer', 'pointer']);
  const cast = new NativeFunction(Module.getGlobalExportByName('__dynamic_cast'),
    'pointer', ['pointer', 'pointer', 'pointer', 'long'], {exceptions: 'propagate'});
  const refType = module.getExportByName('_ZTIN7cocos2d3RefE');
  const bannerType = module.getExportByName('_ZTI9BannerMst');
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN16GateMissionScene22setLayoutSubHeaderAreaEPN7cocos2d15SpriteBatchNodeES2_S2_'), {
    onEnter(args) {
      const dungeon = args[0].add(0x5f8).readPointer();
      headerRaids.push(dungeon.isNull() ? null : rewardIds.get(dungeon.add(0x24).readS32()));
    },
    onLeave() { headerRaids.pop(); }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN13BannerMstList15getListWithTypeEi'), {
    onEnter(args) {
      // GL9's raid header enumerates type 3 and takes its first active entry.
      // Keep that original path, but give it only this archived raid's entry.
      if (args[1].toInt32() === 3) this.expected = headerRaids[headerRaids.length - 1];
    },
    onLeave(result) {
      if (!this.expected || result.isNull()) return;
      const data = result.add(0x30).readPointer(), count = data.readU32();
      if (count > 10000) return;
      const entries = data.add(0x10).readPointer(), selected = makeArray();
      let found = false;
      for (let i = 0; i < count; ++i) {
        const item = entries.add(i * Process.pointerSize).readPointer();
        const banner = cast(item, refType, bannerType, 0);
        if (!banner.isNull() && banner.add(0x40).readS32() === this.expected) {
          append(selected, item);
          found = true;
          break;
        }
      }
      result.replace(selected);
      note('LOCAL_RAID_REWARDS_SELECTED banner=' + this.expected + ' found=' + found);
    }
  }));
  const battleState = fn('_ZN11BattleState6sharedEv', 'pointer', []);
  const playerParty = fn('_ZN11BattleState14getPlayerPartyEv', 'pointer', ['pointer']);
  const battleUnits = fn('_ZN11BattleParty17getBattleUnitListEv', 'pointer', ['pointer']);
  const isPlayer = fn('_ZN10BattleUnit12isPlayerUnitEv', 'bool', ['pointer']);
  function unitId(unit) {
    // BattleUnit::getUserUnitID copies the libc++ string at +0x918.
    const value = unit.add(0x918), tag = value.readU8();
    const length = (tag & 1) ? value.add(8).readU64().toNumber() : tag >> 1;
    if (length < 1 || length > 40) throw new Error('Invalid native battle unit ID');
    return ((tag & 1) ? value.add(16).readPointer() : value.add(1)).readUtf8String(length);
  }
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN19MissionChallengeLog16addUseSpecialLogEP10BattleUniti'), {
    onEnter(args) {
      const skill = args[2].toInt32();
      if (!bridge || (skill !== 501560 && skill !== 501580) || !isPlayer(args[1])) return;
      try {
        const party = playerParty(battleState());
        if (party.isNull()) return;
        const array = battleUnits(party);
        if (array.isNull()) return;
        const data = array.add(0x30).readPointer(), count = data.readU32();
        if (count < 1 || count > 6) return;
        const entries = data.add(0x10).readPointer(), ids = [];
        for (let i = 0; i < count; ++i) {
          const unit = entries.add(i * Process.pointerSize).readPointer();
          if (isPlayer(unit)) ids.push(unitId(unit));
        }
        const actor = unitId(args[1]);
        bridge('raidAction', '(Ljava/lang/String;ILjava/lang/String;)Z', [actor, skill, JSON.stringify(ids)], 'bool');
      } catch (error) {
        note('LOCAL_RAID_SEQUENCE_ERROR ' + error);
      }
    }
  }));
  // The original scene reads the selected BannerMst's own local rewards URL.
}
