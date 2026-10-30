import globalBundles from '../server/global_bundles.json';
import namedSummons from '../server/gacha_named.json';
import curatedSummons from '../server/gacha_authored.json';

export function modeFields(rows) {
  return rows.flatMap((row, rowIndex) => {
    const fields = Object.entries(row);
    return fields.map(([key, value], column) => ({row: rowIndex, column, key,
      value: String(value), last: column === fields.length - 1 ? 1 : 0}));
  });
}

// Add the season chooser to the original GL9 summon header: the game's own
// button skin (GameScale9Sprite), StringLabel, rectangle and scene refresh.
export function installSummonMenu(module, note, retained, bridge, homeCarousel = null) {
  const fn = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const strType = 'RKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE';
  const makeSprite = fn('_ZN16GameScale9Sprite25createWithSpriteFrameNameE' + strType + 'RKN7cocos2d4RectE',
    'pointer', ['pointer', 'pointer']);
  const spriteSize = fn('_ZN16GameScale9Sprite7setSizeEff', 'void', ['pointer', 'float', 'float']);
  const setPosition = fn('_ZN7cocos2d4Node11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const setAnchor = fn('_ZN7cocos2d4Node14setAnchorPointERKNS_4Vec2E', 'void', ['pointer', 'pointer']);
  const frameCache = fn('_ZN7cocos2d16SpriteFrameCache11getInstanceEv', 'pointer', []);
  const findFrame = fn('_ZN7cocos2d16SpriteFrameCache20getSpriteFrameByNameE' +
    'RKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE', 'pointer', ['pointer', 'pointer']);
  // StringLabel::init(layer, text, x, y, colour, style, size); GameLayer::addChild(layer, z, node).
  const makeLabel = fn('_ZN9GameScene14setStringLabelEi' + strType + 'ffRKN7cocos2d7Color3BEiii',
    'pointer', ['pointer', 'int', 'pointer', 'float', 'float', 'pointer', 'int', 'int', 'int']);
  const layer = fn('_ZN9GameLayer6sharedEv', 'pointer', []);
  const addChild = fn('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'int', 'pointer']);
  const removeChild = fn('_ZN9GameLayer11removeChildEiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'pointer']);
  const touchEnabled = fn('_ZN9GameScene13isTouchEnableEv', 'bool', ['pointer']);
  const sceneState = fn('_ZNK13GachaTopScene13getSceneStateEv', 'int', ['pointer']);
  const setTab = fn('_ZN13GachaTopScene6setTabENS_9GACHA_TABE', 'void', ['pointer', 'int']);
  const scrollPosition = fn('_ZN9LayerUtil13setScrollPosYEiiii', 'void', ['int', 'int', 'int', 'int']);
  const refresh = fn('_ZN9GameScene24onCheckTouchFooterSummonEv', 'void', ['pointer']);
  const eventTab = fn('_ZN9GateScene6setTabENS_8GATE_TABE', 'void', ['pointer', 'int']);
  const refreshEvents = fn('_ZN9GateScene13refreshLayoutEb', 'void', ['pointer', 'bool']);
  let eventAreas = new Set(), visibleEvents = new Set();
  const eventLists = new Map(), eventTabs = new Map(), eventAnchors = new Map();
  let eventAliases = {};
  let eventModes = {}, eventDungeons = {}, dungeonNames = {}, modeDungeonIds = new Set();
  let gateTouchDepth = 0, dungeonMenuDepth = 0, enteringModeDepth = 0;
  const gateTouches = [];
  const inModeChooser = () => !enteringModeDepth && (gateTouchDepth > 0 || dungeonMenuDepth > 0);
  const assignModeTitle = fn('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6assignEPKcm',
    'pointer', ['pointer', 'pointer', 'uint64']);
  let compactModeHeader = null;
  for (const [symbol, title] of [
    ['_ZN11TfaTopScene13initSubHeaderEv', 'Clash of Wills'],
    ['_ZN19TfaRewardsViewScene13initSubHeaderEv', 'Clash Rewards'],
    ['_ZN15TfaRankingScene13initSubHeaderEv', 'Clash Rankings']
  ]) retained.push(Interceptor.attach(module.getExportByName(symbol), {
    onEnter() { this.previous = compactModeHeader; compactModeHeader = title; },
    onLeave() { compactModeHeader = this.previous; }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GameScene12setSubHeaderENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEffiibb'), {
    onEnter(args) {
      // The by-value argument belongs to the caller and remains normally destroyed.
      if (compactModeHeader) assignModeTitle(args[1], Memory.allocUtf8String(compactModeHeader), compactModeHeader.length);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZNK7AreaMst11getAreaNameEv'), {
    onEnter(args) {
      const mode = eventModes[String(args[0].add(0x88).readS32())];
      this.title = mode === 'tfa' ? 'Clash of Wills' : mode === 'parade' ? 'Dark Visions' : null;
      this.output = this.context.x8;
    },
    onLeave() {
      // The original getter constructs a by-value string in x8. Assign into
      // that owned result; campaign names remain on the season/stage rows.
      if (this.title) assignModeTitle(this.output, Memory.allocUtf8String(this.title), this.title.length);
    }
  }));
  const width = fn('_ZN11CommonUtils11getWinWidthEv', 'int', []);
  const height = fn('_ZN11CommonUtils12getWinHeightEv', 'int', []);
  const rectangle = fn('_ZN12GraphicUtils8fillRectEiffffRKN7cocos2d7Color3BEiib',
    'pointer', ['int', 'float', 'float', 'float', 'float', 'pointer', 'int', 'int', 'bool']);
  const color = (r, g, b) => Memory.alloc(3).writeByteArray([r, g, b]);
  const white = color(255, 255, 255), black = color(0, 0, 0);
  const popupBackground = color(0, 17, 38), popupBorder = color(90, 135, 180);
  const popupSelected = color(22, 64, 105);
  const caps = Memory.alloc(16).writeByteArray(new Uint8Array(16));
  const centre = Memory.alloc(8);
  centre.writeFloat(0.5); centre.add(4).writeFloat(0.5);
  const scenes = new Map();
  const layerId = 101, z = 29000;
  // The chooser sits in the header row (Back / "Summon"), on its empty right side
  // above the Limited Time tab. Design units: 640 wide, y measured from the top.
  const headerX = ui => ui.kind === 'event' ? (eventAnchors.get(ui.scene.toString())?.x || width() - 164) : width() - 103;
  const headerY = ui => ui.kind === 'event' ? (eventAnchors.get(ui.scene.toString())?.y || 55) : 188;
  const headerW = ui => ui.kind === 'event' ? 112 : 190;
  const headerH = ui => ui.kind === 'event' ? 70 : 50;
  const rowH = 28;
  let skin, eventMenu;
  function archiveData(method, selection) {
    return JSON.parse(bridge(method, '(Ljava/lang/String;)Ljava/lang/String;', [selection]));
  }

  function withString(value, action) {
    // Read-only libc++ string references, as used by the existing loading hook.
    // Frida owns both buffers; none is handed to a C++ string destructor.
    const length = Array.from(value).reduce((n, c) => n + (c.codePointAt(0) < 128 ? 1 :
      c.codePointAt(0) < 2048 ? 2 : c.codePointAt(0) < 65536 ? 3 : 4), 0);
    const s = Memory.alloc(24);
    s.writeByteArray(new Uint8Array(24));
    let buffer;
    if (length <= 22) { s.writeU8(length * 2); s.add(1).writeUtf8String(value); }
    else {
      const capacity = Math.ceil((length + 1) / 16) * 16;
      buffer = Memory.alloc(capacity);
      buffer.writeUtf8String(value);
      s.writeU64(capacity | 1); s.add(8).writeU64(length); s.add(16).writePointer(buffer);
    }
    const result = action(s);
    // Keep long text alive until the native reader has returned.
    if (buffer) buffer.isNull();
    return result;
  }
  function label(ui, key, text, x, y, size = 18, depth = z + 4) {
    const previous = ui.labels.get(key);
    if (previous) removeChild(layer(), layerId, previous);
    if (!text) { ui.labels.delete(key); return; }
    const node = withString(text, s => makeLabel(ui.scene, layerId, s, x, y, white, 1, size, depth));
    ui.labels.set(key, node);
  }
  function chooseSkin() {
    // The first original button frame the summon screen has loaded.
    const loaded = ['tab_off.png', 'common_tab_bg.png', 'sort_btn_mini_1.png', 'sort_btn5_1.png',
                    'common_btn_mini_oldui_off.png', 'common_btn_gdsquare_blue.png', 'common_btn_gdsquare_off.png',
                    'gacha_tab_free_1.png', 'common_tab_bg_black.png']
      .filter(name => !withString(name, s => findFrame(frameCache(), s)).isNull());
    note('LOCAL_SUMMON_GROUP_SKINS loaded=' + loaded.join(','));
    return loaded[0] || null;
  }
  function panel(ui, x, y, w, h, depth) {
    // A button face centred on (x, y). Falls back to a plain dark box if no skin is loaded.
    let node;
    if (skin) {
      node = withString(skin, s => makeSprite(s, caps));
      spriteSize(node, w, h);
      setAnchor(node, centre);
      setPosition(node, x, height() - y);
      addChild(layer(), layerId, depth, node);
    } else {
      node = rectangle(layerId, x - w / 2, y - h / 2, w, h, black, depth, 220, 0);
    }
    ui.nodes.push(node);
    return {x, y, w, h};
  }
  function hit(box, point) {
    return box && Math.abs(point.x - box.x) <= box.w / 2 && Math.abs(point.y - box.y) <= box.h / 2;
  }
  function touchPoint(touch) {
    // cocos2d::Touch::_point (+0x34): the view-space point, top-left origin, in design
    // units; Touch::getLocation only flips it with Director::convertToGL.
    return {x: touch.add(0x34).readFloat(), y: touch.add(0x38).readFloat()};
  }
  function readMenu(selection = '', kind = 'summon') {
    const result = kind === 'event' && !selection && eventMenu ? eventMenu :
      archiveData(kind === 'event' ? 'eventArchive' : 'summonArchive', selection);
    if (kind === 'event') {
      eventMenu = result;
      eventAliases = result.area_aliases || {};
      eventModes = result.native_modes || {};
      eventDungeons = result.native_dungeons || {};
      dungeonNames = result.dungeon_names || {};
      modeDungeonIds = new Set(result.mode_dungeon_ids || []);
      eventAreas = new Set(result.area_ids.map(Number));
      visibleEvents = new Set(result.selected.ids.map(Number));
    }
    Object.assign(bannerNames, result.names || {});
    Object.assign(explanations, result.explanations || {});
    for (const id of result.limited_steps || []) limitedStepIds.add(Number(id));
    return result;
  }
  // Banners the shipped text table does not name (community, named): the detail header asks
  // TextManager for MST_GACHA_NAME_<id> and printed the key. Answer with the engine's name.
  // getText returns a const reference, so each string stays allocated for the session.
  const bannerNames = {}, nameStrings = {};
  // Local bundles have no row in the shipped text table either; the Shop printed MST_BUNDLE_NAME_<id>.
  const bundleNames = Object.fromEntries([['990000001', '2,000 Friend Points'],
    ...globalBundles.bundles.map(bundle => [String(bundle.id), bundle.name])]);
  // The JP special summons' ticket items (F_ITEM_MST 106213030-080) have no Global English name.
  const itemNames = {'106213040': 'SP Summon Ticket', '106213050': '4★/5★/NV SP Summon Ticket',
    '106213030': '5★/NV SP Summon Ticket', '106213060': 'Bonus Summon Ticket',
    '106213070': 'Boss Rush Summon Ticket', '106213080': 'Brave Ability Box Ticket'};
  const compactHeaders = {
    PARADE_PARTY_REGISTER_SLOT_LIST_SAVE_SUB_HEADER: 'Save Party',
    PARADE_PARTY_REGISTER_SLOT_LIST_LOAD_SUB_HEADER: 'Load Party'
  };
  const explanations = Object.fromEntries(namedSummons.banners.map(banner => [String(banner.id),
    (banner.steps ? `${banner.steps.length}-step summon. Review each step's contents above.` :
      `Summon ${banner.draws || 1} reward${banner.draws === 1 ? '' : 's'}. The button shows the cost.`)]));
  const nameFor = id => id.startsWith('header:') ? compactHeaders[id.slice(7)] :
    id.startsWith('explain:') ? explanations[id.slice(8)] :
    id.startsWith('area:') ? ({tfa: 'Clash of Wills', parade: 'Dark Visions'}[eventModes[id.slice(5)]]) :
    id.startsWith('dungeon:') ? dungeonNames[id.slice(8)] :
    id.startsWith('bundle:') ? bundleNames[id.slice(7)] :
    id.startsWith('item:') ? itemNames[id.slice(5)] : bannerNames[id];
  const utf8Length = value => Array.from(value).reduce((n, c) => n + (c.codePointAt(0) < 128 ? 1 :
    c.codePointAt(0) < 2048 ? 2 : c.codePointAt(0) < 65536 ? 3 : 4), 0);
  const nameHook = {
    onEnter(args) {
      const flag = args[1].readU8();
      const length = (flag & 1) ? args[1].add(8).readU64().toNumber() : flag >>> 1;
      this.id = null;
      if (length > 15 && length < 96) {
        const key = ((flag & 1) ? args[1].add(16).readPointer() : args[1].add(1)).readUtf8String(length);
        if (compactHeaders[key]) this.id = 'header:' + key;
        else if (key.startsWith('MST_AREA_NAME_') && eventModes[key.slice(14)])
          this.id = 'area:' + key.slice(14);
        else if (key.startsWith('MST_GACHA_EXPLAIN_LONG_'))
          this.id = 'explain:' + key.slice('MST_GACHA_EXPLAIN_LONG_'.length);
        else if (key.startsWith('MST_GACHA_EXPLAIN_SHORT_'))
          this.id = 'explain:' + key.slice('MST_GACHA_EXPLAIN_SHORT_'.length);
        else if (key.startsWith('MST_GACHA_NAME_')) this.id = key.slice(15);
        else if (key.startsWith('MST_BUNDLE_NAME_')) this.id = 'bundle:' + key.slice(16);
        else if (key.startsWith('MST_ITEM_NAME_')) this.id = 'item:' + key.slice(14);
        else if (key.startsWith('MST_BUNDLE_DESC_')) this.id = 'bundle:' + key.slice(16);
      }
    },
    onLeave(result) {
      if (!this.id || nameFor(this.id) === undefined) return;
      if (!nameStrings[this.id]) {
        const name = nameFor(this.id), length = utf8Length(name);
        const s = Memory.alloc(24), buffer = Memory.alloc(Math.ceil((length + 1) / 16) * 16);
        buffer.writeUtf8String(name);
        s.writeU64(uint64(Math.ceil((length + 1) / 16) * 16).or(1)); s.add(8).writeU64(length); s.add(16).writePointer(buffer);
        nameStrings[this.id] = [s, buffer];
      }
      result.replace(nameStrings[this.id][0]);
    }
  };
  // Local bundles never expire (end date 2099), and the Early Bird popup printed "Ends in: 26731 day(s)".
  // Show the list tiles' "-" instead for any end ten years or more away. The string is returned in x8.
  const endTime = module.findExportByName('_ZNK10BundleInfo19getFormattedEndTimeEv');
  if (endTime) retained.push(Interceptor.attach(endTime, {
    onEnter() { this.out = this.context.x8; },
    onLeave() {
      const out = this.out, flag = out.readU8();
      const length = (flag & 1) ? out.add(8).readU64().toNumber() : flag >>> 1;
      if (length > 64) return;
      const value = ((flag & 1) ? out.add(16).readPointer() : out.add(1)).readUtf8String(length);
      // Only a bare day count (a dated format has more than one number).
      const numbers = value.match(/\d+/g) || [];
      if (numbers.length !== 1 || Number(numbers[0]) < 3650) return;
      out.writeByteArray(new Uint8Array(24));
      out.writeU8(2);
      out.add(1).writeUtf8String('-');
    }
  }));
  // Every banner is served without an end (Elv, 2026-10-24: they always stay available), so the list's
  // date strip read "06/09/2022 07:00 - 01/01/2100 06:59". Keep only the real start date. The label text
  // is edited in place: the new text is shorter, so it fits the string's own buffer.
  const neverEnds = /^(\d\d\/\d\d\/\d{4} \d\d:\d\d) - \d\d\/\d\d\/2100 \d\d:\d\d$/;
  const trimDate = text => {
    const flag = text.readU8(), long = (flag & 1) !== 0;
    const length = long ? text.add(8).readU64().toNumber() : flag >>> 1;
    if (length < 30 || length > 40) return;
    const data = long ? text.add(16).readPointer() : text.add(1);
    const match = neverEnds.exec(data.readUtf8String(length));
    if (!match) return;
    data.writeUtf8String(match[1]);
    if (long) text.add(8).writeU64(match[1].length);
    else text.writeU8(match[1].length * 2);
  };
  for (const [name, index] of [['_ZN7cocos2d5Label9setStringERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE', 1],
                               ['_ZN15StringLabelList12changeStringE' + strType, 1],
                               ['_ZN15StringLabelList12changeStringE' + strType + 'S8_', 1],
                               ['_ZN9GameScene14setStringLabelEi' + strType + 'ffRKN7cocos2d7Color3BEiii', 2]]) {
    const address = module.findExportByName(name);
    if (address) retained.push(Interceptor.attach(address, { onEnter(args) { trimDate(args[index]); } }));
  }
  // Shop carousel check (2026-10-25): the Shop top builds one ScrlBundleBanner per bundle from its banner
  // icon; log the first paths it asks for and whether an image was made. Remove once the carousel shows.
  const createBanner = module.findExportByName('_ZN21GachaBannerDownloader12createBannerERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEERKN7cocos2d4SizeE');
  let bannerLogs = 0;
  if (createBanner) retained.push(Interceptor.attach(createBanner, {
    onEnter(args) {
      const flag = args[0].readU8(), length = (flag & 1) ? args[0].add(8).readU64().toNumber() : flag >>> 1;
      this.path = length < 300 ? ((flag & 1) ? args[0].add(16).readPointer() : args[0].add(1)).readUtf8String(length) : '';
    },
    onLeave(result) {
      if (/bundle/.test(this.path) && bannerLogs++ < 12) note('SHOP_BANNER ' + this.path + ' -> ' + result);
    }
  }));
  // Offline ticket/FP offers have no promotional art. Keep them in Bundles,
  // but omit their empty pages from the original Shop carousel.
  const bannerLayout = module.getExportByName('_ZN12ShopTopScene15setBannerLayoutEv');
  const makeArray = fn('_ZN7cocos2d7__Array6createEv', 'pointer', []);
  const appendObject = fn('_ZN7cocos2d7__Array9addObjectEPNS_3RefE', 'void', ['pointer', 'pointer']);
  const retainObject = fn('_ZN7cocos2d3Ref6retainEv', 'void', ['pointer']);
  const releaseObject = fn('_ZN7cocos2d3Ref7releaseEv', 'void', ['pointer']);
  // Factory results own one Ref, as in the original response reader. Each
  // class reads C strings synchronously; finish it before releasing that Ref.
  const responseFactory = fn('_ZN19GameResponseFactory18createResponseDataEPKcb',
    'pointer', ['pointer', 'bool']);
  const responseClasses = {
    L6XRZb0z: 'TfaEventInfoResponse', x51bb135: 'TfaStatusInfoResponse',
    Fs0sexp7: 'TfaUserBonusRewardInfoResponse', AJb8pF71: 'TfaUserArchiveInfoResponse',
    XHnyfiwg: 'TfaUserArchiveInfoResponse', cBHNnXQZ: 'TfaRankingInfoListResponse',
    Q4kJKh8b: 'RmEventInfoResponse',
    Wmr7y9a0: 'UserRmInfoResponse', jSC4Tx9H: 'UserRmActualInfoResponse',
    Ur6CKS2e: 'RmResumeInfoResponse',
    gXrD1h58: 'ParadeEventInfoResponse', yA8Nn9vK: 'UserParadeInfoResponse',
    '94IYZAbg': 'UserParadeArchiveInfoNowResponse', HMa5VTU8: 'ParadeWinningResultInfoResponse',
    sMPhc96i: 'RoyalParadeEntryInfoResponse', EYa5g4wh: 'UserParadeArchiveInfoResponse',
    fqTUI1z6: 'UserPartyDeckInfoResponse', zeucwm6H: 'UserPartyDeckInfoResponse',
    DW7uH6Mn: 'UnitEquipResponse', wc8vSHPS: 'UnitEquipResponse',
    REbh19u0: 'UserBeastDeckInfoResponse', g8ZuTVvQ: 'UserBeastDeckInfoResponse',
    '8PEB5o7G': 'UserActualInfoResponse', GV7Ej6n0: 'UserPartyDeckInfoResponse',
    VE7KZ8CY: 'UnitEquipResponse', qVX5Lab8: 'UserBeastDeckInfoResponse'
  };
  const modeReaders = {};
  for (const [tag, name] of Object.entries(responseClasses)) {
    const member = method => '_ZN' + name.length + name + method.length + method + 'Ev';
    const callback = method => {
      const own = module.findExportByName(member(method));
      return own ? new NativeFunction(own, 'void', ['pointer'], {exceptions: 'propagate'}) :
        fn('_ZN12ResponseData' + method.length + method + 'Ev', 'void', ['pointer']);
    };
    modeReaders[tag] = {
      start: callback('onReadStarted'), finish: callback('onReadFinished'),
      read: fn('_ZN' + name.length + name + '9readParamEiiPKcS1_b',
        'void', ['pointer', 'int', 'int', 'pointer', 'pointer', 'bool'])
    };
  }
  const sumallyList = fn('_ZN20SumallyRewardMstList6sharedEv', 'pointer', []);
  const sumallyRewards = fn('_ZN20SumallyRewardMstList13getRewardListEi', 'pointer', ['pointer', 'int']);
  const sumallyParser = fn('_ZN20SumallyRewardMstList12createParserEv', 'pointer', ['pointer']);
  const readSumally = fn('_ZN24SumallyRewardMstResponse9readParamEiiPKcS1_b',
    'void', ['pointer', 'int', 'int', 'pointer', 'pointer', 'bool']);
  // shared() is inline in the pinned client. The response reader initializes
  // this exported singleton before prepareClashRanking uses it.
  const tfaInfo = module.getExportByName('_ZZN12TfaEventInfo6sharedEvE9singleton');
  const setSumallyId = fn('_ZN12TfaEventInfo12setSumallyIdEi', 'void', ['pointer', 'int']);
  let selectedClashRanking = 0;
  function prepareClashRanking(result) {
    if (result.mode !== 'tfa') return;
    const id = Number(result.ranking_id), rows = result.ranking_rewards;
    if (!id || !Array.isArray(rows) || !rows.length) throw new Error('Missing Clash ranking table');
    const list = sumallyList();
    const count = () => sumallyRewards(list, id).add(0x30).readPointer().readS32();
    if (count() === 0) {
      const parser = sumallyParser(list);
      if (parser.isNull()) throw new Error('Missing native ranking parser');
      try {
        // Its onReadStarted(mode=0) clears the entire master list. Append only
        // the absent season, preserving all other original ranking tables.
        for (const field of modeFields(rows)) readSumally(parser, field.row, field.column,
          Memory.allocUtf8String(field.key), Memory.allocUtf8String(field.value), field.last);
      } finally { releaseObject(parser); }
    }
    const loaded = count();
    if (loaded !== rows.length) throw new Error('Incomplete native Clash ranking table');
    selectedClashRanking = id;
    setSumallyId(tfaInfo, id);
    note('LOCAL_CLASH_RANKING_READY id=' + id + ' rows=' + loaded);
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN19TfaRewardsViewScene10initializeEv'), {
    onEnter(args) {
      if (!selectedClashRanking) return;
      setSumallyId(tfaInfo, selectedClashRanking);
      // initialize skips this assignment when its inherited initialized flag
      // is already set. Repair the scene's own ID before native tab layout.
      const scene = args[0], previous = scene.add(0x678).readS32();
      if (previous !== selectedClashRanking) {
        scene.add(0x678).writeS32(selectedClashRanking);
        scene.add(0x6e4).writeU8(0);
      }
      note('LOCAL_CLASH_RANKING_SCENE id=' + selectedClashRanking + ' previous=' + previous);
    }
  }));
  let rankingReadLogs = 0;
  retained.push(Interceptor.attach(module.getExportByName('_ZN19TfaRewardsViewScene17getRewardInfoListEv'), {
    onEnter(args) { this.scene = args[0]; this.output = this.context.x8; },
    onLeave() {
      if (rankingReadLogs++ >= 12) return;
      const begin = this.output.readPointer(), end = this.output.add(8).readPointer();
      note('LOCAL_CLASH_RANKING_LIST id=' + this.scene.add(0x678).readS32() +
        ' tab=' + this.scene.add(0x6e0).readS32() + ' rows=' + end.sub(begin).toInt32() / Process.pointerSize);
    }
  }));
  const changeScene = fn('_ZN9GameScene22changeSceneWithSceneIDEi', 'void', ['pointer', 'int']);
  const areaList = fn('_ZN11AreaMstList6sharedEv', 'pointer', []);
  const findArea = fn('_ZN11AreaMstList20getAreaMstWithAreaIDEi', 'pointer', ['pointer', 'int']);
  const userState = fn('_ZN9UserState6sharedEv', 'pointer', []);
  const setLastArea = fn('_ZN9UserState11setLastAreaEP7AreaMst', 'void', ['pointer', 'pointer']);
  const setLastDungeon = fn('_ZN9UserState14setLastDungeonEP10DungeonMst', 'void', ['pointer', 'pointer']);
  // The original GateScene subtype-12 branch allocates 0x610 bytes, calls
  // ParadeEntryScene's constructor and transfers it to changeScene(BaseScene*,bool).
  // Only operator new is a C++ runtime export; every game export stays module scoped.
  const allocateScene = new NativeFunction(Module.getGlobalExportByName('_Znwm'), 'pointer', ['uint64']);
  const paradeEntry = fn('_ZN16ParadeEntrySceneC1Ev', 'void', ['pointer']);
  const paradeArea = fn('_ZN16ParadeEntryScene10setAreaMstEP7AreaMst', 'void', ['pointer', 'pointer']);
  const changeObject = fn('_ZN9GameScene11changeSceneEP9BaseSceneb', 'void', ['pointer', 'pointer', 'bool']);
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GameScene22changeSceneWithSceneIDEi'), {
    onEnter(args) {
      this.mode = [13000, 940000].includes(args[1].toInt32());
      if (this.mode) enteringModeDepth++;
    },
    onLeave() { if (this.mode) enteringModeDepth--; }
  }));
  function prepareMode(dungeon) {
    const info = eventDungeons[String(dungeon)];
    if (!info) return false;
    const result = archiveData('eventArchive', info.mode + ':' + dungeon);
    const groups = Object.entries(result.native_groups || {});
    if (!groups.length || groups.some(([tag]) => !modeReaders[tag]))
      throw new Error('Invalid event response groups');
    for (const [tag, rows] of groups) {
      const reader = modeReaders[tag];
      const response = responseFactory(Memory.allocUtf8String(tag), 0);
      if (response.isNull()) throw new Error('Missing event response ' + tag);
      try {
        reader.start(response);
        for (const field of modeFields(rows)) reader.read(response, field.row, field.column,
          Memory.allocUtf8String(field.key), Memory.allocUtf8String(field.value), field.last);
        reader.finish(response);
      } finally { releaseObject(response); }
    }
    prepareClashRanking(result);
    return result;
  }
  function enterMode(scene, dungeon, selectedDungeon) {
    enteringModeDepth++;
    try {
      const result = prepareMode(dungeon);
      if (!result) return false;
      note('LOCAL_EVENT_MODE dungeon=' + dungeon + ' scene=' + result.scene);
      const area = findArea(areaList(), Number(result.area));
      if (area.isNull()) throw new Error('Unknown selected event area');
      const state = userState();
      setLastArea(state, area);
      // Bypassing GateMissionScene also bypasses its selected-dungeon setup.
      // TFA checks UserState's dungeon for its period and start conditions.
      setLastDungeon(state, selectedDungeon);
      if (result.mode === 'parade') {
        const event = result.native_groups.gXrD1h58[0];
        state.add(0x224).writeS32(Number(event.RdV4nK8w));
        const entry = allocateScene(0x610);
        paradeEntry(entry);
        paradeArea(entry, area);
        changeObject(scene, entry, 1);
      } else changeScene(scene, Number(result.scene));
    } finally { enteringModeDepth--; }
    return true;
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE'), {
    onEnter(args) { gateTouchDepth++; gateTouches.push({scene: args[0], touch: args[1]}); },
    onLeave() { gateTouches.pop(); gateTouchDepth--; }
  }));
  for (const method of ['10initializeEv', '9setLayoutEv', '13setListLayoutEv',
                        '17setDungeonMstListEv', '23getInSessionDungeonListEi']) {
    retained.push(Interceptor.attach(module.getExportByName('_ZN16GateDungeonScene' + method), {
      onEnter() { dungeonMenuDepth++; }, onLeave() { dungeonMenuDepth--; }
    }));
  }
  // A previously saved RM run must not intercept Parade's subtype dispatch.
  retained.push(Interceptor.attach(module.getExportByName('_ZN6RmUtil13getNowAreaMstEv'), {
    onLeave(value) {
      if (gateTouchDepth && !enteringModeDepth && !value.isNull() &&
          eventModes[String(value.add(0x88).readS32())] === 'parade') value.replace(ptr(0));
    }
  }));
  // Grouped mode campaigns first use the original dungeon list to choose a
  // season. Preserve mission subtypes everywhere outside this menu dispatch.
  retained.push(Interceptor.attach(module.getExportByName('_ZN11MissionUtil22getFirstMissionSubTypeEi'), {
    onEnter(args) { this.area = inModeChooser() ? String(args[0].toInt32()) : ''; },
    onLeave(value) {
      if (!eventModes[this.area]) return;
      if (eventAliases[this.area]?.length) { value.replace(0); return; }
      if (eventModes[this.area] === 'parade') {
        const entry = Object.entries(eventDungeons).find(([, info]) => info.area === this.area && info.entry);
        if (entry) try { prepareMode(Number(entry[0])); }
        catch (error) { note('LOCAL_EVENT_MODE_ERROR ' + error.stack); }
      }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene5isTFAEv'), {
    onEnter(args) {
      const area = args[0].add(0x5f8).readPointer();
      const aid = area.isNull() ? '' : String(area.add(0x88).readS32());
      this.grouped = inModeChooser() && !!eventAliases[aid]?.length && !!eventModes[aid];
    },
    onLeave(value) { if (this.grouped) value.replace(0); }
  }));
  const chooseDungeonAddress = module.getExportByName('_ZN16GateDungeonScene18changeMissionSceneEv');
  const chooseDungeonCallback = new NativeCallback(scene => {
    const selected = scene.add(0x5f0).readPointer();
    if (!selected.isNull() && eventDungeons[String(selected.add(0x24).readS32())]) {
      try { enterMode(scene, selected.add(0x24).readS32(), selected); }
      catch (error) { note('LOCAL_EVENT_MODE_ERROR ' + error.stack); }
      return;
    }
    originalChooseDungeon(scene);
  }, 'void', ['pointer']);
  const originalChooseDungeon = new NativeFunction(Interceptor.replaceFast(chooseDungeonAddress, chooseDungeonCallback),
    'void', ['pointer'], {exceptions: 'propagate'});
  retained.push(chooseDungeonCallback);
  const cast = new NativeFunction(Module.getGlobalExportByName('__dynamic_cast'),
    'pointer', ['pointer', 'pointer', 'pointer', 'long'], {exceptions: 'propagate'});
  const refType = module.getExportByName('_ZTIN7cocos2d3RefE');
  const areaType = module.getExportByName('_ZTI7AreaMst');
  const getLayouts = fn('_ZN9GameScene18getLayoutCacheListEv', 'pointer', ['pointer']);
  const getLayout = fn('_ZN15LayoutCacheList9getObjectE' + strType + 'b', 'pointer', ['pointer', 'pointer', 'bool']);
  const visible = fn('_ZN7cocos2d4Node10setVisibleEb', 'void', ['pointer', 'bool']);
  const gateHeaders = [];
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene22setLayoutSubHeaderAreaEv'), {
    onEnter(args) { gateHeaders.push(args[0]); },
    onLeave() {
      const scene = gateHeaders.pop();
      const layouts = getLayouts(scene);
      if (layouts.isNull()) return;
      const layout = withString('seal_area_icon', key => getLayout(layouts, key, 1));
      if (!layout.isNull()) eventAnchors.set(scene.toString(), {
        x: layout.add(0x24).readFloat() + layout.add(0x2c).readFloat() / 2,
        y: layout.add(0x28).readFloat() + layout.add(0x30).readFloat() / 2
      });
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN9GameScene30createSpriteButtonForBatchNodeEiffiP10GameSpriteS1_S1_S1_t'), {
    onEnter(args) {
      this.oldSeals = gateHeaders.length && args[2].toInt32() === 101;
      if (!this.oldSeals) return;
      // Keep the existing header layout, but retire the keyed replay action.
      // All event missions remain available through the archive filter.
      this.sprites = [args[3], args[5]];
      args[2] = ptr(-65001);
    },
    onLeave() {
      if (this.oldSeals) for (const sprite of this.sprites)
        if (!sprite.isNull()) visible(sprite, 0);
    }
  }));
  const dungeonListAddress = module.getExportByName('_ZN14DungeonMstList24getDungeonListWithAreaIdEi');
  const dungeonList = new NativeFunction(dungeonListAddress, 'pointer', ['pointer', 'int'], {exceptions: 'propagate'});
  let collectingDungeons = false;
  retained.push(Interceptor.attach(dungeonListAddress, {
    onEnter(args) {
      const aid = String(args[1].toInt32()), nativeMode = !!eventModes[aid];
      this.mode = !collectingDungeons && nativeMode && inModeChooser();
      this.aliases = collectingDungeons || (nativeMode && !this.mode) ? null :
        (eventAliases[aid] || (this.mode ? [] : null));
      this.list = args[0];
    },
    onLeave(result) {
      if (!this.aliases || result.isNull()) return;
      collectingDungeons = true;
      try {
        const combined = makeArray(), seen = new Set();
        for (const items of [result, ...this.aliases.map(id => dungeonList(this.list, Number(id)))]) {
          if (items.isNull()) continue;
          const data = items.add(0x30).readPointer(), count = data.readU32();
          if (count > 10000) throw new Error('Invalid campaign dungeon list');
          const entries = data.add(0x10).readPointer();
          for (let i = 0; i < count; i++) {
            const entry = entries.add(i * Process.pointerSize).readPointer(), key = entry.toString();
            const did = entry.isNull() ? '' : String(entry.add(0x24).readS32());
            if (this.mode && modeDungeonIds.has(did) && !eventDungeons[did]?.entry) continue;
            if (!entry.isNull() && !seen.has(key)) {
              appendObject(combined, entry);
              seen.add(key);
            }
          }
        }
        result.replace(combined);
      } catch (error) { note('LOCAL_EVENT_DUNGEON_MERGE_ERROR ' + error); }
      finally { collectingDungeons = false; }
    }
  }));
  const carouselIds = new Set(globalBundles.bundles.filter(b => b.art).map(b => Number(b.id)));
  retained.push(Interceptor.attach(bannerLayout, {
    onEnter(args) {
      try {
        // GL9 setBannerLayout iterates this scene-owned __Array at +0x5d8.
        // Build a separate image-only list; keep the master and purchase list intact.
        const slot = args[0].add(0x5d8), pages = slot.readPointer();
        if (pages.isNull()) return;
        const data = pages.add(0x30).readPointer(), before = data.readU32();
        const entries = data.add(0x10).readPointer(), filtered = makeArray();
        let count = 0;
        for (let i = 0; i < before; i++) {
          const info = entries.add(i * Process.pointerSize).readPointer();
          if (!info.isNull() && carouselIds.has(info.add(0x24).readS32())) {
            appendObject(filtered, info);
            count++;
          }
        }
        if (count > 0) {
          retainObject(filtered);
          slot.writePointer(filtered);
          releaseObject(pages);
        }
        note('SHOP_CAROUSEL images=' + count + ' omitted_empty=' + (before - count));
      } catch (error) { note('SHOP_CAROUSEL_ERROR ' + error.stack); }
    }
  }));
  // Archive placement must not replace native step-up type 5 with type 50.
  const limitedStepIds = new Set([...namedSummons.banners, ...curatedSummons.banners]
    .filter(b => b.steps && b.tab === 'limited')
    .map(b => Number(b.id)));
  for (const [method, result] of [['_ZN8GachaMst9isPayTypeEv', 0], ['_ZN8GachaMst13isLimitedTypeEv', 1]]) {
    retained.push(Interceptor.attach(module.getExportByName(method), {
      onEnter(args) { this.localStep = limitedStepIds.has(args[0].add(0x30).readS32()); },
      onLeave(value) { if (this.localStep) value.replace(result); }
    }));
  }
  // The detail header reads its name with getMstText; other screens use getText.
  for (const name of ['_ZN11TextManager7getTextE', '_ZN11TextManager10getMstTextE'])
    retained.push(Interceptor.attach(module.getExportByName(name + strType), nameHook));
  function clear(ui) {
    for (const node of ui.nodes) removeChild(layer(), layerId, node);
    ui.nodes = [];
    for (const key of Array.from(ui.labels.keys())) label(ui, key, '', 0, 0);
  }
  function drawHeader(ui) {
    ui.header = panel(ui, headerX(ui), headerY(ui), headerW(ui), headerH(ui), z + 5);
    if (ui.kind === 'event') {
      label(ui, 'filter', 'Filter', headerX(ui) - headerW(ui) / 2 + 14, headerY(ui) - 18, 18, z + 6);
      label(ui, 'header', ui.menu.selected.label + ' ▼', headerX(ui) - headerW(ui) / 2 + 10, headerY(ui) + 6, 15, z + 6);
    } else label(ui, 'header', ui.menu.selected.label + '  ▼', headerX(ui) - headerW(ui) / 2 + 16, headerY(ui), 20, z + 6);
  }
  function close(ui) {
    ui.open = false;
    ui.rows = [];
    clear(ui);
    drawHeader(ui);
  }
  function open(ui) {
    clear(ui);
    ui.open = true;
    // Dim the screen behind the list; the list drops down from the header button.
    ui.nodes.push(rectangle(layerId, 0, 0, width(), height(), black, z, 150, 0));
    drawHeader(ui);
    const left = headerX(ui) - 95, top = headerY(ui) + headerH(ui) / 2;
    const listHeight = ui.menu.groups.length * rowH;
    ui.nodes.push(rectangle(layerId, left - 1, top - 1, 192, listHeight + 2, popupBorder, z + 2, 255, 0));
    ui.nodes.push(rectangle(layerId, left, top, 190, listHeight, popupBackground, z + 3, 255, 0));
    ui.rows = ui.menu.groups.map((group, i) => {
      const y = top + rowH * (i + 0.5);
      const box = {x: headerX(ui), y, w: 190, h: rowH};
      if (group.id === ui.menu.selected.id)
        ui.nodes.push(rectangle(layerId, left, top + rowH * i, 190, rowH, popupSelected, z + 3, 255, 0));
      const mark = group.id === ui.menu.selected.id ? '▶ ' : '';
      label(ui, 'choice' + i, mark + group.label + ' (' + group.count + ')', left + 12, y - 12, 17);
      return {box, group};
    });
    note('LOCAL_GROUP_POPUP kind=' + ui.kind + ' x=' + headerX(ui) + ' top=' + top + ' row=' + rowH);
  }
  function choose(ui, group) {
    ui.menu = readMenu(group.id, ui.kind);
    close(ui);
    if (ui.kind === 'event') {
      eventTab(ui.scene, 0);
      // The original refresh releases old button actions and clears the
      // scroll layer before rebuilding it. Drawing the rows directly left
      // stale hit targets beneath the newly filtered banners.
      refreshEvents(ui.scene, 1);
      note('LOCAL_EVENT_GROUP_SELECTED id=' + group.id);
      return;
    }
    setTab(ui.scene, ui.menu.selected.tab);
    for (let tab = 0; tab < 3; tab++) scrollPosition(700, tab, 0, 0);
    // The original Summon entry request loads the chosen group's banners
    // and rebuilds the existing tabs and list.
    refresh(ui.scene);
    note('LOCAL_SUMMON_GROUP_SELECTED id=' + group.id);
  }
  for (const [prefix, kind] of [['13GachaTopScene', 'summon'], ['9GateScene', 'event']])
    retained.push(Interceptor.attach(module.getExportByName('_ZN' + prefix + '13initSubHeaderEv'), {
    onEnter(args) { this.scene = args[0]; },
    onLeave() {
      try {
        const key = this.scene.toString();
        let ui = scenes.get(key);
        if (!ui) {
          ui = {scene: this.scene, kind, labels: new Map(), nodes: [], rows: [], open: false};
          scenes.set(key, ui);
        }
        if (skin === undefined) skin = chooseSkin();
        ui.menu = readMenu('', kind);
        close(ui);
        note('LOCAL_SUMMON_GROUP_BUTTON_READY selected=' + ui.menu.selected.id + ' skin=' + skin +
             ' win=' + width() + 'x' + height());
      } catch (error) { note('LOCAL_SUMMON_GROUP_UI_ERROR kind=' + kind + ' ' + error.stack); }
    }
    }));
  // Filter the scene-owned AreaMst array, which is what GateScene actually
  // enumerates. Period checks only affect dates and cannot hide its banners.
  // The original master lists and mission availability remain intact.
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene10initializeEv'), {
    onEnter() {
      try { readMenu('', 'event'); }
      catch (error) { note('LOCAL_EVENT_GROUP_DATA_ERROR ' + error); }
    }
  }));
  function restoreEventList(scene) {
    const key = scene.toString(), saved = eventLists.get(key);
    if (!saved) return;
    const slot = scene.add(0x658), current = slot.readPointer();
    if (current.equals(saved.filtered)) {
      slot.writePointer(saved.original); // transfer the retained reference back
      releaseObject(current);
    } else releaseObject(saved.original);
    eventLists.delete(key);
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene6setTabENS_8GATE_TABE'), {
    onEnter(args) {
      restoreEventList(args[0]);
      eventTabs.set(args[0].toString(), args[1].toInt32());
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GateScene13setListLayoutEbiN7cocos2d4Vec2E'), {
    onEnter(args) {
      const scene = args[0], key = scene.toString();
      if ((eventTabs.get(key) || 0) !== 0 || !eventAreas.size) return;
      try {
        restoreEventList(scene);
        const slot = scene.add(0x658), original = slot.readPointer();
        if (original.isNull()) return;
        const data = original.add(0x30).readPointer(), count = data.readU32();
        if (count > 10000) throw new Error('Invalid Vortex area list');
        const entries = data.add(0x10).readPointer(), filtered = makeArray();
        let kept = 0;
        for (let i = 0; i < count; i++) {
          const area = entries.add(i * Process.pointerSize).readPointer();
          if (area.isNull()) continue;
          // GL9 reads AreaMst+0x88 before getSpDungeonCondMstWithAreaId.
          const info = cast(area, refType, areaType, 0);
          if (info.isNull()) throw new Error('Vortex list contains an invalid area');
          const id = info.add(0x88).readS32();
          if (!eventAreas.has(id) || visibleEvents.has(id)) {
            appendObject(filtered, area);
            kept++;
          }
        }
        retainObject(original);
        retainObject(filtered);
        slot.writePointer(filtered);
        releaseObject(original);
        eventLists.set(key, {original, filtered});
        note('LOCAL_EVENT_GROUP_LIST visible=' + kept + ' total=' + count);
      } catch (error) { note('LOCAL_EVENT_GROUP_LIST_ERROR ' + error); }
    }
  }));
  // Handle modal gestures before GameScene's wrapper dispatches to both the
  // scene and its native banner buttons. Handling only GateScene::touchEnded
  // still lets GameScene::buttonTouchEnded open a banner on the same release.
  let touchLogs = 0;
  function claims(scene, touch) {
    const ui = scenes.get(scene.toString());
    if (ui && touchLogs < 12) {
      touchLogs += 1;
      const p = touchPoint(touch);
      note('LOCAL_SUMMON_GROUP_TOUCH x=' + p.x.toFixed(0) + ' y=' + p.y.toFixed(0) + ' enabled=' +
           touchEnabled(scene) + ' state=' + (ui.kind === 'event' ? 'event' : sceneState(scene)) +
           ' hit=' + hit(ui.header, p));
    }
    if (!ui) return null;
    return ui.open || hit(ui.header, touchPoint(touch)) ? ui : null;
  }
  const chooserTouches = new Map();
  const touchKey = (scene, touch) => scene.toString() + ':' + touch.toString();
  function stopTouch(event) {
    // libgame.so Event constructor and EventDispatcher both use +0x28 for
    // Event::_isStopped. stopPropagation is inline in this original build.
    if (!event.isNull()) event.add(0x28).writeU8(1);
  }
  let touchEnded;
  const endGesture = (scene, touch, event) => {
    const gesture = chooserTouches.get(touchKey(scene, touch));
    if (!gesture) return touchEnded(scene, touch, event);
    stopTouch(event);
    if (gesture.ended) return 1;
    gesture.ended = true;
    if (gesture.home) {
      homeCarousel.end(scene, touch, event);
      return 1;
    }
    const ui = scenes.get(scene.toString());
    if (!ui) return 1;
    if (!touchEnabled(scene) || (ui.kind !== 'event' && sceneState(scene) !== 2)) return 1;
    try {
      const point = touchPoint(touch);
      if (!ui.open && hit(ui.header, point)) {
        ui.menu = readMenu('', ui.kind);
        open(ui);
      } else if (ui.open) {
        const row = ui.rows.find(item => hit(item.box, point));
        note('LOCAL_GROUP_CHOICE kind=' + ui.kind + ' x=' + point.x + ' y=' + point.y + ' id=' + (row?.group.id || 'outside'));
        if (row) choose(ui, row.group);
        else close(ui);
      }
    } catch (error) { note('LOCAL_SUMMON_GROUP_UI_ERROR ' + error); close(ui); }
    return 1;
  };
  const ended = new NativeCallback(endGesture, 'bool', ['pointer', 'pointer', 'pointer']);
  touchEnded = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN9GameScene12onTouchEndedEPN7cocos2d5TouchEPNS0_5EventE'), ended),
    'bool', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  retained.push(ended);
  let touchBegan;
  function claimGesture(scene, touch, event) {
    const key = touchKey(scene, touch);
    chooserTouches.delete(key);
    try {
      if (homeCarousel?.begin(scene, touch)) {
        chooserTouches.set(key, {ended: false, home: true});
        stopTouch(event);
        return true;
      }
      if (claims(scene, touch)) {
        chooserTouches.set(key, {ended: false});
        stopTouch(event);
        return true;
      }
    } catch (error) { note('LOCAL_SUMMON_GROUP_UI_ERROR ' + error); }
    return false;
  }
  const began = new NativeCallback((scene, touch, event) => {
    if (claimGesture(scene, touch, event)) return 1;
    return touchBegan(scene, touch, event);
  }, 'bool', ['pointer', 'pointer', 'pointer']);
  touchBegan = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN9GameScene12onTouchBeganEPN7cocos2d5TouchEPNS0_5EventE'), began),
    'bool', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  retained.push(began);
  let touchMoved;
  const moved = new NativeCallback((scene, touch, event) => {
    if (chooserTouches.has(touchKey(scene, touch))) {
      if (chooserTouches.get(touchKey(scene, touch)).home) homeCarousel.move(scene, touch);
      stopTouch(event);
      return 1;
    }
    return touchMoved(scene, touch, event);
  }, 'bool', ['pointer', 'pointer', 'pointer']);
  touchMoved = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN9GameScene12onTouchMovedEPN7cocos2d5TouchEPNS0_5EventE'), moved),
    'bool', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  retained.push(moved);
  let touchCancelled;
  const cancelled = new NativeCallback((scene, touch, event) => {
    const key = touchKey(scene, touch);
    if (chooserTouches.has(key)) {
      if (chooserTouches.get(key).home) homeCarousel.cancel(scene);
      chooserTouches.delete(key);
      stopTouch(event);
      return;
    }
    touchCancelled(scene, touch, event);
  }, 'void', ['pointer', 'pointer', 'pointer']);
  touchCancelled = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN9GameScene16onTouchCancelledEPN7cocos2d5TouchEPNS0_5EventE'), cancelled),
    'void', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  retained.push(cancelled);
  // GL9 also registers the all-at-once path. Its wrapper calls the scene's
  // virtual touchesEnded and then buttonTouchEnded directly, bypassing the
  // single-touch wrapper above. Both paths must honor the same modal gesture.
  const vectorSuffix = 'ERKNSt6__ndk16vectorIPN7cocos2d5TouchENS0_9allocatorIS4_EEEEPNS2_5EventE';
  function vectorTouches(vector) {
    const first = vector.readPointer(), last = vector.add(Process.pointerSize).readPointer();
    const bytes = last.sub(first).toInt32();
    if (bytes < 0 || bytes > Process.pointerSize * 16 || bytes % Process.pointerSize) return [];
    const touches = [];
    for (let offset = 0; offset < bytes; offset += Process.pointerSize)
      touches.push(first.add(offset).readPointer());
    return touches;
  }
  for (const [method, length, phase] of [
    ['onTouchesBegan', 14, 'begin'], ['onTouchesMoved', 14, 'move'],
    ['onTouchesEnded', 14, 'end']
  ]) {
    let original;
    const callback = new NativeCallback((scene, vector, event) => {
      const touches = vectorTouches(vector);
      if (phase === 'begin') {
        let claimed = false;
        for (const touch of touches) claimed = claimGesture(scene, touch, event) || claimed;
        if (claimed) return;
      } else {
        const owned = touches.filter(touch => chooserTouches.has(touchKey(scene, touch)));
        if (owned.length) {
          stopTouch(event);
          if (phase === 'end') for (const touch of owned) endGesture(scene, touch, event);
          if (phase === 'move') for (const touch of owned)
            if (chooserTouches.get(touchKey(scene, touch)).home) homeCarousel.move(scene, touch);
          return;
        }
      }
      original(scene, vector, event);
    }, 'void', ['pointer', 'pointer', 'pointer']);
    original = new NativeFunction(Interceptor.replaceFast(
      module.getExportByName('_ZN9GameScene' + length + method + vectorSuffix), callback),
      'void', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
    retained.push(callback);
  }
  // onTouchesCancelled is a 12-byte virtual tail call in GL9 and cannot take
  // a replacement trampoline. It never dispatches a button release. A new
  // begin or scene exit clears any gesture left by cancellation on that path.
  for (const prefix of ['13GachaTopScene', '9GateScene', '9HomeScene']) {
  retained.push(Interceptor.attach(module.getExportByName('_ZN' + prefix + '16onSceneInvisibleEv'), {
    onEnter(args) {
      if (prefix === '9GateScene') restoreEventList(args[0]);
      if (prefix === '9HomeScene') homeCarousel?.leave(args[0]);
      const key = args[0].toString(), ui = scenes.get(key);
      for (const gesture of chooserTouches.keys())
        if (gesture.startsWith(key + ':')) chooserTouches.delete(gesture);
      if (ui) {
        clear(ui);
        scenes.delete(key);
      }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN' + prefix + 'D1Ev'), {
    onEnter(args) {
      if (prefix === '9GateScene') {
        restoreEventList(args[0]);
        eventTabs.delete(args[0].toString());
        eventAnchors.delete(args[0].toString());
      }
      scenes.delete(args[0].toString());
    }
  }));
  }
  // Banner detail buttons. The pay scene puts the single pull in the left slot, the 11 Summons
  // row in the centre slot and the ticket in the right slot (GachaPayDetailScene::
  // setSingleButtonLayout / setMultiButtonLayout). With no ticket button the pair sat left of
  // centre; move both slots right by half a slot so the pair is centred. A lone button already
  // uses the centre slot. The slot positions are restored once each button is laid out.
  const getObject = fn('_ZN15LayoutCacheList9getObjectE' + strType + 'b', 'pointer', ['pointer', 'pointer', 'bool']);
  const usesTicket = fn('_ZN14GachaDetailMst11isUseTicketEv', 'bool', ['pointer']);
  const slot = (scene, name) => withString(name, s => getObject(scene.add(0x430).readPointer(), s, 1));
  function pairShift(scene) {
    const single = scene.add(0x640).readPointer(), multi = scene.add(0x648).readPointer();
    if (single.isNull() || multi.isNull()) return null;
    const mst = scene.add(0x630).readPointer();
    if ((mst.isNull() || mst.add(0x8c).readS32() !== 6) && usesTicket(single)) return null;
    const left = slot(scene, 'gacha_pay_summon_left_btn'), centre = slot(scene, 'gacha_pay_summon_center_btn');
    if (left.isNull() || centre.isNull()) return null;
    return (centre.add(0x24).readFloat() - left.add(0x24).readFloat()) / 2;
  }
  for (const [name, slotName] of [['_ZN19GachaPayDetailScene21setSingleButtonLayoutEv', 'gacha_pay_summon_left_btn'],
                                  ['_ZN19GachaPayDetailScene20setMultiButtonLayoutEv', 'gacha_pay_summon_center_btn']])
    retained.push(Interceptor.attach(module.getExportByName(name), {
      onEnter(args) {
        this.cache = null;
        try {
          const shift = pairShift(args[0]);
          if (!shift) return;
          this.cache = slot(args[0], slotName);
          this.x = this.cache.add(0x24).readFloat();
          this.cache.add(0x24).writeFloat(this.x + shift);
        } catch (error) { note('SUMMON_BUTTON_CENTRE_ERROR ' + error); }
      },
      onLeave() { if (this.cache) this.cache.add(0x24).writeFloat(this.x); }
    }));
  // Offline build: no social sharing. AppSharingScene::setShareButtonUI builds the "Share" button
  // (summon results and other screens) into scene+0x5d8; keep the object, but hide it and ignore taps.
  const buttonVisible = fn('_ZN12SpriteButton12setIsVisibleEb', 'void', ['pointer', 'bool']);
  const buttonTouch = fn('_ZN12SpriteButton14setTouchEnableEb', 'void', ['pointer', 'bool']);
  retained.push(Interceptor.attach(module.getExportByName('_ZN15AppSharingScene16setShareButtonUIEiiffff'), {
    onEnter(args) { this.scene = args[0]; },
    onLeave() {
      const button = this.scene.add(0x5d8).readPointer();
      if (button.isNull()) return;
      buttonVisible(button, 0);
      buttonTouch(button, 0);
    }
  }));
  retained.push(white, black, caps, centre);
  const assign = fn('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6assignEPKcm',
    'pointer', ['pointer', 'pointer', 'uint64']);
  for (const [symbol, offset] of [['_ZN23sgGachaDropRateWebScene6getUrlEv', 0],
    ['_ZThn1504_N23sgGachaDropRateWebScene6getUrlEv', -0x5e0]]) {
    retained.push(Interceptor.attach(module.getExportByName(symbol), {
      onEnter(args) { this.scene = args[0].add(offset); this.out = this.context.x8; },
      onLeave() {
        const banner = this.scene.add(0x67c).readS32();
        if (banner <= 0) return;
        const url = 'http://127.0.0.1/exvius/gacha-rates/' + banner + '.html';
        assign(this.out, Memory.allocUtf8String(url), url.length);
      }
    }));
  }
  for (const symbol of ['_ZN17ParadeRewardScene6getUrlEv', '_ZThn1504_N17ParadeRewardScene6getUrlEv']) {
    retained.push(Interceptor.attach(module.getExportByName(symbol), {
      onEnter() { this.out = this.context.x8; },
      onLeave() {
        const url = 'http://127.0.0.1/exvius/parade-rewards.html';
        assign(this.out, Memory.allocUtf8String(url), url.length);
      }
    }));
  }
  for (const symbol of ['_ZN17EquipGrowTopScene6getUrlEv', '_ZThn1504_N17EquipGrowTopScene6getUrlEv']) {
    retained.push(Interceptor.attach(module.getExportByName(symbol), {
      onEnter() { this.out = this.context.x8; },
      onLeave() {
        const url = 'http://127.0.0.1/exvius/equipment-enhancement.html';
        assign(this.out, Memory.allocUtf8String(url), url.length);
      }
    }));
  }
  // Completion uses the existing WebView. Ranking uses the original native
  // SumallyRewardMst table linked by the TfaEventInfo response.
  for (const symbol of ['_ZN19TfaRewardsViewScene6getUrlEv', '_ZThn1504_N19TfaRewardsViewScene6getUrlEv']) {
    const address = module.findExportByName(symbol);
    if (!address) continue;
    retained.push(Interceptor.attach(address, {
      onEnter() { this.out = this.context.x8; },
      onLeave() {
        const url = 'http://127.0.0.1/exvius/clash-rewards.html';
        assign(this.out, Memory.allocUtf8String(url), url.length);
      }
    }));
  }
  // The original inner-banner fallback adds captions beside its texture.
  // Name seasons there without changing dungeon names on their native maps.
  return dungeon => dungeonNames[String(dungeon)];
}
