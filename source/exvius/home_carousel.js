// Restore the original Home carousel, including visible locked entries.
export function homeMenuState(esperCount, expeditionFlag) {
  return {espers: {visible: true, open: esperCount > 0},
    expedition: {visible: expeditionFlag !== 0, open: expeditionFlag === 2}};
}
export function carouselItems(position, count, width) {
  return Array.from({length: count}, (_, index) => {
    const distance = (((index - position + count / 2) % count) + count) % count - count / 2;
    const focus = Math.max(0, 1 - Math.abs(distance));
    return {index, distance, x: width / 2 + distance * width * 344 / 640,
      scale: 0.75 + focus * 0.25, opacity: Math.round(153 + focus * 102)};
  });
}

export function carouselRelease(start, dx, width) {
  if (Math.abs(dx) < 14) return {position: Math.round(start), dragged: false};
  const movement = -dx / (width * 344 / 640);
  const steps = Math.max(1, Math.round(Math.abs(movement)));
  return {position: Math.round(start) + Math.sign(movement) * steps, dragged: true};
}

export function carouselHit(cards, point) {
  // Neighbouring illustrations overlap. The foreground card owns the shared
  // region, matching the sprites' drawing order rather than catalogue order.
  return cards.filter(card => card.box && Math.abs(point.x - card.box.x) <= card.box.w / 2 &&
    Math.abs(point.y - card.box.y) <= card.box.h / 2)
    .sort((a, b) => b.order - a.order || cards.indexOf(b) - cards.indexOf(a))[0];
}

export function installHomeCarousel(module, note, retained) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args,
    {exceptions: 'propagate'});
  const getIconAddress = module.getExportByName('_ZNK16HomeMainMenuIcon7getIconEv');
  // Pinned GL9 getter: ldr x0,[x0,#0x60]; ret. HomeScene's four owned
  // HomeMainMenuIcon pointers are at +0x700, +0x708, +0x710 and +0x718.
  if (getIconAddress.readU32() !== 0xf9403000 || getIconAddress.add(4).readU32() !== 0xd65f03c0)
    throw new Error('Unexpected original Home icon layout');
  const getIcon = new NativeFunction(getIconAddress, 'pointer', ['pointer'], {exceptions: 'propagate'});
  const width = native('_ZN11CommonUtils14getScreenWidthEv', 'int', []);
  const height = native('_ZN11CommonUtils12getWinHeightEv', 'int', []);
  const size = native('_ZNK7cocos2d4Node14getContentSizeEv', 'pointer', ['pointer']);
  const anchor = native('_ZNK7cocos2d4Node14getAnchorPointEv', 'pointer', ['pointer']);
  const x = native('_ZNK7cocos2d4Node12getPositionXEv', 'float', ['pointer']);
  const y = native('_ZNK7cocos2d4Node12getPositionYEv', 'float', ['pointer']);
  const scaleX = native('_ZNK7cocos2d4Node9getScaleXEv', 'float', ['pointer']);
  const scaleY = native('_ZNK7cocos2d4Node9getScaleYEv', 'float', ['pointer']);
  // Only GameSprite owns the UI point at +0x548. Select original setters
  // through actual RTTI rather than assuming a type from a factory's name.
  const gamePosition = native('_ZN10GameSprite11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const spritePosition = native('_ZN7cocos2d6Sprite11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const nodePosition = native('_ZN7cocos2d4Node11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const spriteScale = native('_ZN7cocos2d6Sprite8setScaleEff', 'void', ['pointer', 'float', 'float']);
  const nodeScale = native('_ZN7cocos2d4Node8setScaleEff', 'void', ['pointer', 'float', 'float']);
  const nodeOpacity = native('_ZN7cocos2d4Node10setOpacityEh', 'void', ['pointer', 'uchar']);
  const spriteVisible = native('_ZN7cocos2d6Sprite10setVisibleEb', 'void', ['pointer', 'bool']);
  const nodeVisible = native('_ZN7cocos2d4Node10setVisibleEb', 'void', ['pointer', 'bool']);
  const cast = new NativeFunction(Module.getGlobalExportByName('__dynamic_cast'), 'pointer',
    ['pointer', 'pointer', 'pointer', 'long'], {exceptions: 'propagate'});
  const nodeType = module.getExportByName('_ZTIN7cocos2d4NodeE');
  const spriteType = module.getExportByName('_ZTIN7cocos2d6SpriteE');
  const gameType = module.getExportByName('_ZTI10GameSprite');
  const types = new Map();
  function typed(object) {
    const key = object.toString();
    if (!types.has(key)) {
      // These fields are already Node pointers, as used by the original
      // layout. Match the proven Node-to-Sprite cast in android_display.js.
      // __dynamic_cast is not an identity/upcast helper for Ref or Node.
      types.set(key, {node: object, sprite: cast(object, nodeType, spriteType, 0),
        game: cast(object, nodeType, gameType, 0)});
    }
    return types.get(key);
  }
  function visible(object, value) {
    const t = typed(object);
    if (t.sprite.isNull()) nodeVisible(t.node, value);
    else spriteVisible(t.sprite, value);
  }
  const stopActions = native('_ZN7cocos2d4Node14stopAllActionsEv', 'void', ['pointer']);
  const holdNode = native('_ZN7cocos2d3Ref6retainEv', 'void', ['pointer']);
  const dropNode = native('_ZN7cocos2d3Ref7releaseEv', 'void', ['pointer']);
  const detachNode = native('_ZN7cocos2d4Node26removeFromParentAndCleanupEb', 'void', ['pointer', 'bool']);
  const hideOrbs = native('_ZN16HomeMainMenuIcon13setVisibleOrbEbb', 'void', ['pointer', 'bool', 'bool']);
  const hideTap = native('_ZN16HomeMainMenuIcon23setVisibleIconTapSpriteEb', 'void', ['pointer', 'bool']);
  const frameCache = native('_ZN7cocos2d16SpriteFrameCache11getInstanceEv', 'pointer', []);
  const findFrame = native('_ZN7cocos2d16SpriteFrameCache20getSpriteFrameByNameERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE',
    'pointer', ['pointer', 'pointer']);
  const makeSprite = native('_ZN7cocos2d6Sprite21createWithSpriteFrameEPNS_11SpriteFrameE', 'pointer', ['pointer']);
  const makeGameSprite = native('_ZN10GameSprite25createWithSpriteFrameNameERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE', 'pointer', ['pointer']);
  const makeEmpty = native('_ZN10GameSprite16createGameSpriteEv', 'pointer', []);
  const intrinsicSize = native('_ZN7cocos2d4Node14setContentSizeERKNS_4SizeE', 'void', ['pointer', 'pointer']);
  const constructString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc', 'void', ['pointer', 'pointer']);
  const destroyString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev', 'void', ['pointer']);
  const layers = native('_ZN9GameLayer6sharedEv', 'pointer', []);
  const addChild = native('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'int', 'pointer']);
  // Reconnect the retained original carousel renderer. The v9 Home scene no
  // longer constructs it. Its pinned constructor writes through +0x44f.
  const allocate = new NativeFunction(Module.getGlobalExportByName('_Znwm'), 'pointer', ['ulong']);
  const rotateCtor = native('_ZN18HomeRotateMenuListC2Ev', 'void', ['pointer']);
  const rotateSize = native('_ZN18HomeRotateMenuList7setSizeEff', 'void', ['pointer', 'float', 'float']);
  const rotateButton = native('_ZN18HomeRotateMenuList17setMenuIconButtonEP12SpriteButton', 'void', ['pointer', 'pointer']);
  const rotateAdd = native('_ZN18HomeRotateMenuList9addObjectEiff', 'void', ['pointer', 'int', 'float', 'float']);
  const rotateUpdate = native('_ZN18HomeRotateMenuList14updatePositionEffi', 'void', ['pointer', 'float', 'float', 'int']);
  const nodeOrder = native('_ZN7cocos2d4Node14setLocalZOrderEi', 'void', ['pointer', 'int']);
  // SpriteButton::initForChangeSprite is a static factory, not an instance
  // initializer. The original factory owns and retains both sprite states.
  const makeButton = native('_ZN12SpriteButton19initForChangeSpriteEiffiP10GameSpriteS1_ib', 'pointer',
    ['int', 'float', 'float', 'int', 'pointer', 'pointer', 'int', 'bool']);
  const buttonPressed = native('_ZN12SpriteButton17changeTouchSpriteEv', 'void', ['pointer']);
  const buttonNormal = native('_ZN12SpriteButton18changeNormalSpriteEv', 'void', ['pointer']);
  const buttonEnable = native('_ZN12SpriteButton11setIsEnableEb', 'void', ['pointer', 'bool']);
  const spriteFrame = native('_ZN7cocos2d6Sprite14setSpriteFrameEPNS_11SpriteFrameE', 'void', ['pointer', 'pointer']);
  const setArenaOrbs = native('_ZN18HomeRotateMenuList10setClsmOrbEiffffP10GameSpriteNSt6__ndk16vectorIS1_NS2_9allocatorIS1_EEEE',
    'void', ['pointer', 'int', 'float', 'float', 'float', 'float', 'pointer', 'pointer']);
  const updateArenaOrbs = native('_ZN18HomeRotateMenuList16updateClsmOrbNumEiiii', 'void', ['pointer', 'int', 'int', 'int', 'int']);
  const ssList = native('_ZN13SS5PlayerList6sharedEv', 'pointer', []);
  const ssAdd = native('_ZN13SS5PlayerList9addPlayerERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_iiiiii',
    'pointer', ['pointer', 'pointer', 'pointer', 'int', 'int', 'int', 'int', 'int', 'int']);
  const ssRemove = native('_ZN13SS5PlayerList11removeAnimeEPN2ss6PlayerE', 'void', ['pointer', 'pointer']);
  const ssPosition = native('_ZN2ss6Player11setPositionEii', 'void', ['pointer', 'int', 'int']);
  const loadAtlas = native('_ZN7cocos2d16SpriteFrameCache23addSpriteFramesWithFileERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE',
    'void', ['pointer', 'pointer']);
  const beasts = native('_ZN17UserBeastInfoList6sharedEv', 'pointer', []);
  const expeditionManager = native('_ZN13sgExpdManager6sharedEv', 'pointer', []);
  const expeditionFlag = native('_ZNK13sgExpdManager14getFeatureFlagEv', 'int', ['pointer']);
  const arenaOpen = native('_ZN9HomeScene13isOpenedArenaEv', 'bool', ['pointer']);
  // Home needs the permanent Item World entry, not a scan of every archived
  // story/event mission. 7860101 is the shipped subtype-6 first floor. Keep
  // the native borrowed master pointer and all non-Home lookups unchanged.
  const missions = native('_ZN14MissionMstList6sharedEv', 'pointer', []);
  const mission = native('_ZN14MissionMstList13getMissionMstEi', 'pointer', ['pointer', 'int']);
  let homeMissionThread = null;
  for (const symbol of ['_ZN9HomeScene10initializeEv', '_ZN9HomeScene18updateMainMenuIconEv',
                        '_ZN9HomeScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE'])
    retained.push(Interceptor.attach(module.getExportByName(symbol), {
      onEnter() { this.previous = homeMissionThread; homeMissionThread = this.threadId; this.started = Date.now(); },
      onLeave() {
        homeMissionThread = this.previous;
        if (Date.now() - this.started > 100) note('HOME_NATIVE_LAYOUT method=' + symbol + ' ms=' + (Date.now() - this.started));
      }
    }));
  let originalMission;
  const homeMission = new NativeCallback(function (kind) {
    if (kind === 6 && homeMissionThread === Process.getCurrentThreadId()) return mission(missions(), 7860101);
    const started = Date.now(), result = originalMission(kind);
    if (Date.now() - started > 100) note('HOME_MISSION_LOOKUP kind=' + kind + ' scope=' + homeMissionThread +
      ' thread=' + Process.getCurrentThreadId() + ' ms=' + (Date.now() - started));
    return result;
  }, 'pointer', ['int']);
  originalMission = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN8GateUtil22getInSessionMissionMstEi'), homeMission),
    'pointer', ['int'], {exceptions: 'propagate'});
  retained.push(homeMission);
  const expeditionCtor = native('_ZN18sgExpdConnectSceneC1Ev', 'void', ['pointer']);
  const expeditionRequestCtor = native('_ZN22sgExpdQuestInfoRequestC1Ev', 'void', ['pointer']);
  const expeditionParam = native('_ZN18sgExpdConnectScene8setParamEP11RequestDatai',
    'void', ['pointer', 'pointer', 'int']);
  const changeStep = native('_ZN9GameScene15changeStepSceneEPS_b', 'void', ['pointer', 'pointer', 'bool']);
  const changeScene = native('_ZN9GameScene22changeSceneWithSceneIDEi', 'void', ['pointer', 'int']);
  // std::string returns in AAPCS64's indirect result register x8. libffi's
  // 24-byte aggregate return supplies that storage. Destroy the owned result.
  const ssResource = native('_ZN13SS5PlayerList11addResourceERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE',
    ['uint64', 'uint64', 'uint64'], ['pointer', 'pointer']);
  const ssAlpha = native('_ZN2ss6Player8setAlphaEi', 'void', ['pointer', 'int']);
  const ssFrames = native('_ZNK2ss6Player11getMaxFrameEv', 'int', ['pointer']);
  const ssFrame = native('_ZNK2ss6Player10getFrameNoEv', 'int', ['pointer']);
  const getOpacity = native('_ZNK7cocos2d4Node10getOpacityEv', 'uchar', ['pointer']);
  const orbPosition = native('_ZN13BitmapLabelEx13setUIPositionEff', 'void', ['pointer', 'float', 'float']);
  const orbVisible = native('_ZN13BitmapLabelEx10setVisibleEb', 'void', ['pointer', 'bool']);
  const orbText = native('_ZN13BitmapLabelEx12updateStringERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE',
    'void', ['pointer', 'pointer']);
  const orbOpacity = native('_ZN13BitmapLabelEx10setOpacityEi', 'void', ['pointer', 'int']);
  const orbCounts = new Map();
  for (const [symbol, countArgument, maximumArgument] of [
    ['_ZN16HomeMainMenuIcon14setOrbNumLabelEP11LayoutCacheiiii', 4, 5],
    ['_ZN16HomeMainMenuIcon14updateOrbLabelEii', 1, 2]
  ]) retained.push(Interceptor.attach(module.getExportByName(symbol), {
    onEnter(args) {
      const key = args[0].toString(), previous = orbCounts.get(key);
      orbCounts.set(key, {value: args[countArgument].toInt32(), maximum: args[maximumArgument].toInt32(),
        revision: (previous?.revision || 0) + 1});
    }
  }));
  const addNode = native('_ZN7cocos2d4Node8addChildEPS0_ii', 'void', ['pointer', 'pointer', 'int', 'int']);
  function withString(text, action) {
    const value = Memory.alloc(24);
    constructString(value, Memory.allocUtf8String(text));
    try { return action(value); } finally { destroyString(value); }
  }
  function press(ui, card) {
    if (!card.open || card.animation) return;
    ui.pressed = card;
    if (card.button) buttonPressed(card.button);
    else withString('mypage_icon_eg2.png', s => {
      const frame = findFrame(frameCache(), s);
      if (!frame.isNull()) spriteFrame(card.art.node, frame);
    });
  }
  function releasePress(ui) {
    const card = ui.pressed;
    ui.pressed = null;
    if (!card) return;
    if (card.button) buttonNormal(card.button);
    else if (!card.animation) withString('mypage_icon_eg1.png', s => {
      const frame = findFrame(frameCache(), s);
      if (!frame.isNull()) spriteFrame(card.art.node, frame);
    });
  }
  // The v9 party-detail panels sit behind the restored carousel. Hide their
  // complete contents, including labels and gauges, not just the backdrop.
  retained.push(Interceptor.attach(module.getExportByName('_ZN9HomeScene25setMainMenuBackInfoLayoutEv'), {
    onEnter() {
      const thread = this.threadId, nodes = this.nodes = new Map();
      // Collect only while this Home layout is constructed. Global addChild
      // callbacks otherwise run for every node on every screen.
      this.collectors = [
        ['_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE', 3],
        ['_ZN9GameLayer8addChildEiPN7cocos2d4NodeE', 2]
      ].map(([symbol, argument]) => Interceptor.attach(module.getExportByName(symbol), {
        onEnter(args) {
          const node = args[argument];
          if (this.threadId === thread && !node.isNull()) nodes.set(node.toString(), node);
        }
      }));
    },
    onLeave() {
      for (const collector of this.collectors) collector.detach();
      for (const node of this.nodes.values()) visible(node, 0);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN15sgHomeIconUtils10isDispIconEi'), {
    onEnter(args) { this.hidden = [16, 19].includes(args[1].toInt32()); },
    onLeave(result) { if (this.hidden) result.replace(0); }
  }));
  function labelText(label) {
    // BitmapLabelEx::setString starts with add x0,x0,#0x548 in the pinned
    // library. Its text is a libc++ string, not GameSprite's UI-point field.
    if (label.isNull()) return '';
    const text = label.add(0x548), flags = text.readU8();
    const length = flags & 1 ? text.add(8).readU64().toNumber() : flags >>> 1;
    if (length < 0 || length > 256) return '';
    return (flags & 1 ? text.add(16).readPointer() : text.add(1)).readUtf8String(length);
  }
  function currentOrbs(card) {
    const key = card.owner.toString(), label = card.owner.add(0x40).readPointer();
    const ratio = labelText(label).match(/(\d+)\s*\/\s*(\d+)/);
    let count = orbCounts.get(key);
    if (ratio && (!count || count.value !== Number(ratio[1]) || count.maximum !== Number(ratio[2]))) {
      count = {value: Number(ratio[1]), maximum: Number(ratio[2]), revision: (count?.revision || 0) + 1};
      orbCounts.set(key, count);
    }
    return count ? {...count, ratio: !!ratio} : null;
  }
  function artwork(ui, name, depth, game = false, attach = true) {
    const frame = withString(name, s => findFrame(frameCache(), s));
    if (frame.isNull()) throw new Error('Missing original Home artwork: ' + name);
    const node = game ? withString(name, s => makeGameSprite(s)) : makeSprite(frame);
    if (node.isNull()) throw new Error('Cannot create original Home artwork: ' + name);
    holdNode(node);
    ui.artwork.push(node);
    if (attach) addChild(layers(), 13, depth, node);
    return snapshot(node);
  }
  function originalVortex(ui) {
    const resource = withString('spritestudio/home_animation/home_animation.ssbp',
      s => ssResource(ssList(), s));
    const returned = Memory.alloc(24);
    resource.forEach((value, i) => returned.add(i * 8).writeU64(value));
    let key;
    try {
      const flags = returned.readU8(), length = flags & 1 ? returned.add(8).readU64().toNumber() : flags >>> 1;
      if (length <= 0 || length > 128) throw new Error('Invalid original Home animation resource');
      key = (flags & 1 ? returned.add(16).readPointer() : returned.add(1)).readUtf8String(length);
    } finally { destroyString(returned); }
    // Use the original player registry and direct GameLayer attachment. A
    // nested player attached during layout did not advance its scheduled frames.
    const node = withString(key, resourceKey => withString('home_spdungeon/anime', anime =>
      ssAdd(ssList(), resourceKey, anime, 13, 170, 536, 2000, 0, 0)));
    if (node.isNull()) throw new Error('Original Vortex player could not be created');
    holdNode(node);
    ui.players.push(node);
    const frames = ssFrames(node);
    if (frames <= 1) throw new Error('Original Vortex animation did not load');
    nodeScale(node, 0.75, 0.75);
    note('HOME_ORIGINAL_VORTEX resource=' + key + ' frames=' + frames);
    return {art: snapshot(node), animation: node};
  }
  function createArtwork(ui) {
    withString('image/ui/home/mypage_ext2.plist', name => loadAtlas(frameCache(), name));
    ui.background = artwork(ui, 'mypage_bg_bottom.png', 0);
    ui.topRule = artwork(ui, 'mypage_center_frame_top.png', 2);
    ui.bottomRule = artwork(ui, 'mypage_center_frame_bottom.png', 2);
    Object.assign(ui.cards[5], originalVortex(ui));
    ui.cards[6].art = artwork(ui, 'mypage_icon_eg1.png', 3);
    for (const [i, stem] of ['mypage_colosseum', 'mypage_world', 'mypage_expedition', 'mypage_craft', 'mypage_summon'].entries()) {
      const card = ui.cards[i];
      card.stem = stem;
      card.art = artwork(ui, stem + '1.png', 3, true);
      card.locked = withString(stem + '3.png', s => findFrame(frameCache(), s));
      card.unlocked = withString(stem + '1.png', s => findFrame(frameCache(), s));
      if (card.locked.isNull()) throw new Error('Missing original locked artwork: ' + stem);
      const pressed = artwork(ui, stem + '2.png', 3, true);
      card.pressed = pressed.node;
      if (typed(card.art.node).game.isNull()) throw new Error('Original Home mode must use GameSprite');
      // The first integer is the GameLayer (+0x390), and the fourth is the
      // touch ID (+0x304). addLayer reads +0x390 when reattaching the art.
      card.button = makeButton(13, 0, 0, 9100 + i, card.art.node, pressed.node, 2000, 0);
      if (card.button.isNull()) throw new Error('Original Home button creation failed');
      holdNode(card.button); ui.owners.push(card.button);
      // addLayer's final two steps, without its destructive reparenting.
      nodeVisible(card.button, 1);
      buttonEnable(card.button, 1);
      card.renderer = allocate(0x450);
      rotateCtor(card.renderer); ui.owners.push(card.renderer);
      rotateButton(card.renderer, card.button);
      if (i === 0) {
        const plate = artwork(ui, 'mypage_orb_plate.png', 0, true, false);
        const orbs = Array.from({length: 10}, () => artwork(ui, 'mypage_orb_on.png', 0, true, false));
        const data = Memory.alloc(10 * Process.pointerSize), vector = Memory.alloc(3 * Process.pointerSize);
        orbs.forEach((orb, index) => data.add(index * Process.pointerSize).writePointer(orb.node));
        vector.writePointer(data);
        vector.add(Process.pointerSize).writePointer(data.add(10 * Process.pointerSize));
        vector.add(2 * Process.pointerSize).writePointer(data.add(10 * Process.pointerSize));
        // Original legacy orb-plate offset, sphere offset and spacing.
        // setClsmOrb reads this by-value vector through its ABI indirection;
        // it stores the individual sprite pointers, not the temporary vector.
        setArenaOrbs(card.renderer, 0, 0, 44, 4, 21, plate.node, vector);
        card.orbNodes = [plate.node, ...orbs.map(orb => orb.node)];
      }
      // Authored legacy home_btn_world and menu_area: 344x280 within 640x295.
      rotateSize(card.renderer, 344, 280);
      rotateAdd(card.renderer, 13, 0, 0);
    }
  }
  const touchEnabled = native('_ZN9GameScene13isTouchEnableEv', 'bool', ['pointer']);
  const nativeBegin = native('_ZN9HomeScene10touchBeganEPN7cocos2d5TouchEPNS0_5EventE',
    'bool', ['pointer', 'pointer', 'pointer']);
  const nativeEnd = native('_ZN9HomeScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE',
    'bool', ['pointer', 'pointer', 'pointer']);
  const scenes = new Map();
  retained.push(Interceptor.attach(module.getExportByName('_ZN16HomeMainMenuIcon23setVisibleIconTapSpriteEb'), {
    onEnter(args) {
      for (const ui of scenes.values()) {
        if (ui.cards.some(card => card.owner?.equals(args[0]))) { args[1] = ptr(0); break; }
      }
    }
  }));
  function dispose(ui) {
    for (const player of ui.players.splice(0)) {
      ssRemove(ssList(), player);
      dropNode(player);
      types.delete(player.toString());
    }
    for (const node of ui.artwork.splice(0)) {
      types.delete(node.toString());
      detachNode(node, 1);
      dropNode(node);
    }
    for (const node of ui.owners.splice(0).reverse()) {
      detachNode(node, 1);
      dropNode(node);
    }
    for (const card of ui.cards) if (card.held) { card.held = false; dropNode(card.icon.node); }
  }
  let route = null;
  const modeTags = [1, 0, null, null, null, 13, 6];
  // Hidden promotional hit areas still precede the original main-menu tests
  // inside HomeScene. A validated carousel tap belongs only to its chosen mode.
  // Skip these prechecks for that one routed touch without activating a banner.
  for (const symbol of [
    '_ZN14BannerScrlList12onTouchBeganEPN7cocos2d5TouchE',
    '_ZN14BannerScrlList12onTouchEndedEPN7cocos2d5TouchE',
    '_ZN15sgHomeIconUtils21checkBundleTouchBeganEPN7cocos2d5TouchE',
    '_ZN15sgHomeIconUtils21checkBundleTouchEndedEPN7cocos2d5TouchE'
  ]) {
    let original;
    const callback = new NativeCallback((self, touch) => {
      if (route && route.touch.equals(touch)) return 0;
      return original(self, touch);
    }, 'bool', ['pointer', 'pointer']);
    original = new NativeFunction(Interceptor.replaceFast(module.getExportByName(symbol), callback),
      'bool', ['pointer', 'pointer'], {exceptions: 'propagate'});
    retained.push(callback);
  }
  function routeAllowed(scene) {
    return scene.add(0x3c4).readS32() <= 0 && scene.add(0x3a8).readPointer().isNull();
  }
  // The original Home hit map keeps the old fixed card targets. Only during
  // an already validated centre tap, map those tests to the carousel choice.
  // The original handlers still enforce unlocks, capacity and event resume.
  for (const [symbol, nodeArgument, touchArgument] of [
    ['_ZN9BaseScene13isTouchObjectEiPN7cocos2d5TouchEffffb', false, 2],
    ['_ZN9BaseScene13isTouchObjectEPN7cocos2d4NodeEiPNS0_5TouchE', true, 3]
  ]) retained.push(Interceptor.attach(module.getExportByName(symbol), {
    onEnter(args) {
      if (!route || !args[0].equals(route.ui.scene) || !args[touchArgument].equals(route.touch)) return;
      const index = nodeArgument ? route.ui.cards.findIndex(c => c.icon && c.icon.node.equals(args[1])) :
        modeTags.indexOf(args[1].toInt32());
      if (index >= 0) this.forced = routeAllowed(args[0]) && index === route.index ? 1 : 0;
    },
    onLeave(result) { if (this.forced !== undefined) result.replace(this.forced); }
  }));
  const point = touch => ({x: touch.add(0x34).readFloat(), y: touch.add(0x38).readFloat()});
  function snapshot(node) {
    const s = size(node), a = anchor(node);
    return {node, x: x(node), y: y(node), sx: scaleX(node), sy: scaleY(node),
      w: s.readFloat(), h: s.add(4).readFloat(), ax: a.readFloat(), ay: a.add(4).readFloat()};
  }
  function centred(node, px, py, sx, sy, alpha, shown = true) {
    visible(node, shown ? 1 : 0);
    if (!shown) return;
    const t = typed(node), a = anchor(t.node), s = size(t.node);
    if (t.sprite.isNull()) nodeScale(t.node, sx, sy);
    else spriteScale(t.sprite, sx, sy);
    const nx = px + (a.readFloat() - 0.5) * s.readFloat() * sx;
    const ny = py - (a.add(4).readFloat() - 0.5) * s.add(4).readFloat() * sy;
    if (!t.game.isNull()) gamePosition(t.game, nx, ny);
    else if (!t.sprite.isNull()) spritePosition(t.sprite, nx, height() - ny);
    else nodePosition(t.node, nx, height() - ny);
    nodeOpacity(t.node, alpha);
  }
  function draw(ui) {
    if (ui.routing) return;
    // Home's initial server response replaces the placeholder artwork after
    // setLayout. Read the owner's current pointers before touching a sprite.
    // A released placeholder must never remain in this renderer's cache.
    for (const card of ui.cards.filter(c => c.offset)) {
      card.owner = ui.scene.add(card.offset).readPointer();
      const current = getIcon(card.owner), bg = card.owner.add(0x28).readPointer();
      if (!current.equals(card.icon.node)) {
        const previous = card.icon, replacement = snapshot(current);
        holdNode(current);
        card.icon = replacement;
        types.delete(previous.node.toString());
        // Retail updateIcon releases its owner reference but leaves the old
        // child attached. That is invisible with fixed overlapping cards,
        // but becomes a duplicate in a carousel. Our reference keeps it alive
        // until the old child and its atlas quad have been removed safely.
        detachNode(previous.node, 1);
        dropNode(previous.node);
        stopActions(current);
        note('HOME_CAROUSEL_REFRESH mode=' + card.name);
      }
      if (!bg.isNull() && (!card.bg || !bg.equals(card.bg.node))) {
        if (card.bg) types.delete(card.bg.node.toString());
        card.bg = snapshot(bg);
        stopActions(bg);
      }
      if (bg.isNull()) card.bg = null;
      const event = card.owner.add(0x58).readPointer();
      card.event = event.isNull() ? null : event;
    }
    // Legacy layout_home_640x1136: menu_area=(0,659,640,295).
    const w = width(), h = height(), bottom = h - (1136 - 659 - 295);
    ui.cy = bottom - 147.5;
    ui.top = bottom - 295;
    ui.bottomEdge = bottom;
    ui.width = w; ui.height = h;
    if (!ui.background) createArtwork(ui);
    centred(ui.background.node, w / 2, ui.cy, w / 640, 295 / 440, 255);
    centred(ui.topRule.node, w / 2, ui.top - 24, w / 640, 1, 255);
    centred(ui.bottomRule.node, w / 2, bottom + 24, w / 640, 1, 255);
    for (const card of ui.cards.filter(c => c.owner)) {
      visible(card.icon.node, 0);
      hideOrbs(card.owner, 0, 0);
      hideTap(card.owner, 0);
      if (card.event) {
        // HomeMainMenuIcon +0x58 owns a cocos2d::__Array of event images,
        // not a Node. setEventIcon allocates 0x38 bytes and fills that array.
        const data = card.event.add(0x30).readPointer();
        const count = data.readU64().toNumber(), items = data.add(0x10).readPointer();
        for (let index = 0; index < count; index++) {
          const image = items.add(index * Process.pointerSize).readPointer();
          stopActions(image);
          visible(image, 0);
        }
      }
      if (card.bg) visible(card.bg.node, 0);
    }
    const state = homeMenuState(beasts().add(0x30).readPointer().readS32(), expeditionFlag(expeditionManager()));
    ui.cards[0].open = !!arenaOpen(ui.scene);
    ui.cards[1].open = true;
    ui.cards[2].open = state.expedition.open;
    ui.cards[3].open = true;
    ui.cards[4].open = state.espers.open;
    ui.cards[5].open = true;
    // The original Home touch handler checks event availability on entry.
    ui.cards[6].open = true;
    const carousel = [0, 1, 5, 2, 3, 4].map(i => ui.cards[i])
      .filter(c => c.name !== 'Expedition' || state.expedition.visible);
    if (!ui.carousel || carousel.length !== ui.carousel.length) {
      ui.position = 1; ui.snap = null; ui.carousel = carousel;
    }
    for (const card of ui.cards.slice(0, 5)) {
      if (card.lastOpen !== card.open) {
        spriteFrame(card.art.node, card.open ? card.unlocked : card.locked);
        card.lastOpen = card.open;
        note('HOME_UNLOCK mode=' + card.name + ' open=' + card.open);
      }
      if (!carousel.includes(card)) {
        visible(card.art.node, 0); visible(card.pressed, 0); card.box = null;
      }
    }
    drawCarousel(ui);
    // Equipment Enhancement is the separate small Home command in the
    // original layout, not a fourth item fabricated for the sliding strip.
    const vortex = ui.cards[5];
    const now = Date.now();
    if (!ui.animationSamples || (ui.animationSamples === 1 && now - ui.animationStarted >= 1000)) {
      if (!ui.animationSamples) ui.animationStarted = now;
      ui.animationSamples = (ui.animationSamples || 0) + 1;
      note('HOME_ORIGINAL_ANIMATION sample=' + ui.animationSamples + ' frame=' + ssFrame(vortex.animation));
    }
    const equipment = ui.cards[6];
    const equipmentX = 72 * w / 640;
    const equipmentY = 250;
    centred(equipment.art.node, equipmentX, equipmentY, 1, 1, 255);
    equipment.box = {x: equipmentX, y: equipmentY, w: 116, h: 92};
    // setOrbNumLabel owns BitmapLabelEx at +0x40 with ANCHOR_TOP_LEFT.
    // Reuse its live count at layout_home_equip_grow's authored label point.
    const equipmentOrbs = equipment.owner.add(0x40).readPointer();
    if (!equipmentOrbs.isNull()) {
      const count = currentOrbs(equipment);
      const key = equipmentOrbs.toString() + ':' + count?.revision;
      if (count && (count.ratio || ui.orbStyle !== key)) {
        withString(count.value + '/' + count.maximum, text => orbText(equipmentOrbs, text));
        ui.orbStyle = key;
      }
      orbPosition(equipmentOrbs, equipmentX + 14, equipmentY - 24);
      orbVisible(equipmentOrbs, 1);
    }
  }
  // Movement updates only the carousel. Ownership, feature gates and
  // unrelated Home artwork refresh in draw(), outside Android MOVE bursts.
  function drawCarousel(ui) {
    const started = Date.now();
    const carousel = ui.carousel, w = ui.width, h = ui.height;
    for (const item of carouselItems(ui.position, carousel.length, w)) {
      const card = carousel[item.index];
      const arenaCount = card.orbNodes ? currentOrbs(card) : null;
      if (arenaCount) updateArenaOrbs(card.renderer, arenaCount.value, arenaCount.maximum, 0, 1);
      // The original renderer has separate front and dimmed rear paths.
      const angle = item.distance * 2 * Math.PI / carousel.length;
      const front = Math.cos(angle) >= 0;
      const rawX = carousel.length > 3 ? w / 2 + Math.sin(angle) * w * 344 / 640 /
        Math.sin(2 * Math.PI / carousel.length) : item.x;
      const order = (front ? 2000 : 1800) - Math.round(Math.abs(item.distance) * 50);
      card.order = order;
      if (card.animation) {
        // Match HomeRotateMenuList::updatePosition's scale and centre
        // transform. Using its input X directly put the side portal offscreen.
        const distance = Math.abs(rawX - w / 2), ratio = Math.min(1, distance / 344);
        const factor = front ? 1 - 0.25 * ratio : 0.5 + 0.25 * ratio;
        const px = w / 2 + (rawX - w / 2) * factor;
        ssPosition(card.animation, Math.round(px), Math.round(ui.cy));
        const edge = ui.cards[1].renderer.add(0x430).readFloat();
        const alpha = front ? 255 - 102 * ratio :
          51 + 102 * Math.min(1, Math.abs((distance - edge) / (344 - edge)));
        ssAlpha(card.animation, Math.trunc(alpha));
        nodeScale(card.animation, 0.75 * factor, 0.75 * factor);
        nodeOrder(card.animation, order);
        card.box = {x: px, y: ui.cy, w: 240 * factor, h: 240 * factor};
        continue;
      }
      rotateUpdate(card.renderer, rawX, ui.cy, front ? 2000 : 1800);
      nodeOrder(card.art.node, order);
      nodeOrder(card.pressed, order + 1);
      if (card.orbNodes) for (const node of card.orbNodes) nodeOrder(node, order + 1);
      const s = snapshot(card.art.node);
      card.box = {x: s.x, y: h - s.y, w: s.w * s.sx, h: s.h * s.sy};
      if (card.orbNodes) {
        // The original Home owner keeps this BitmapLabelEx countdown live.
        // Move that label with Arena instead of calculating a second timer.
        const timer = card.owner.add(0x50).readPointer();
        if (!timer.isNull()) {
          const shown = arenaCount && arenaCount.value < arenaCount.maximum && labelText(timer).length > 0;
          orbVisible(timer, shown ? 1 : 0);
          if (shown) {
            const t = typed(timer);
            if (t.sprite.isNull()) nodeScale(timer, s.sx, s.sy); else spriteScale(t.sprite, s.sx, s.sy);
            orbPosition(timer, s.x + 13 * s.sx, h - s.y + 58 * s.sy);
            orbOpacity(timer, getOpacity(card.art.node));
          }
        }
      }
    }
    ui.dirty = false;
    if ((ui.renderSamples || 0) < 6) {
      ui.renderSamples = (ui.renderSamples || 0) + 1;
      note('HOME_CAROUSEL_FRAME ms=' + (Date.now() - started));
    }
  }
  function hit(box, p) {
    return box && Math.abs(p.x - box.x) <= box.w / 2 && Math.abs(p.y - box.y) <= box.h / 2;
  }
  function snap(ui, target) {
    ui.snap = {from: ui.position, to: target, time: Date.now()};
    const selected = ((target % ui.carousel.length) + ui.carousel.length) % ui.carousel.length;
    note('HOME_CAROUSEL_FOCUS mode=' + ui.carousel[selected].name);
  }
  function setup(scene) {
    // Keep one renderer reference to each original mode sprite while Home
    // is visible. Replacement and scene exit release those references.
    types.clear();
    const previous = scenes.get(scene.toString());
    if (previous) dispose(previous);
    scenes.delete(scene.toString());
    const cards = [[0x700, 'Arena'], [0x710, 'World'], [0, 'Expedition'], [0, 'Craft'],
      [0, 'Espers'], [0x708, 'Vortex'], [0x718, 'Equipment Enhancement']]
      .map(([offset, name]) => {
        if (!offset) return {offset, name, open: false};
        const owner = scene.add(offset).readPointer();
        if (owner.isNull()) throw new Error('Missing original Home mode ' + name);
        const node = getIcon(owner);
        if (node.isNull()) throw new Error('Missing original Home sprite ' + name);
        const icon = snapshot(node), bgNode = owner.add(0x28).readPointer();
        if (!(icon.w > 0 && icon.h > 0)) throw new Error('Empty Home mode sprite ' + name);
        stopActions(node);
        if (!bgNode.isNull()) stopActions(bgNode);
        return {offset, owner, name, icon, bg: bgNode.isNull() ? null : snapshot(bgNode),
          event: owner.add(0x58).readPointer()};
      });
    for (const card of cards) if (card.event?.isNull()) card.event = null;
    const bg = cards[1].bg, original = bg || cards[1].icon;
    const bottom = height() - original.y + original.ay * original.h * original.sy;
    const ui = {scene, cards, bottom, position: 1, snap: null, gesture: null,
      routing: false, artwork: [], owners: [], players: []};
    scenes.set(scene.toString(), ui);
    for (const card of cards.filter(c => c.icon)) { holdNode(card.icon.node); card.held = true; }
    try { draw(ui); }
    catch (error) { dispose(ui); scenes.delete(scene.toString()); throw error; }
    note('HOME_CAROUSEL_READY width=' + ui.width + ' top=' + ui.top + ' bottom=' + bottom);
    note('HOME_ORIGINAL_BOXES ' + cards.map(c => c.name + ':' + JSON.stringify(c.box)).join(','));
    note('HOME_ORIGINAL_ORBS ' + [cards[0], cards[6]].map(c => c.name + ':' +
      JSON.stringify(currentOrbs(c))).join(','));
    note('HOME_CAROUSEL_TYPES ' + cards.filter(c => c.icon).map(c => c.name + ':' +
      (typed(c.icon.node).game.isNull() ? 'sprite' : 'game') + '/bg:' +
      (c.bg && !typed(c.bg.node).game.isNull() ? 'game' : 'sprite')).join(','));
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN9HomeScene9setLayoutEv'), {
    onEnter(args) { this.scene = args[0]; },
    onLeave() {
      try { setup(this.scene); }
      catch (error) { note('HOME_CAROUSEL_ERROR ' + error); }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9HomeScene11updateEventEv'), {
    onEnter(args) { this.key = args[0].toString(); },
    onLeave() {
      const ui = scenes.get(this.key);
      if (ui) {
        try { draw(ui); }
        catch (error) { dispose(ui); scenes.delete(this.key); note('HOME_CAROUSEL_ERROR ' + error); }
      }
    }
  }));
  // Home's event callback and BaseScene tick do not provide continuous updates
  // for this retained scene. The director callback runs on the render thread.
  retained.push(Interceptor.attach(module.getExportByName('_ZN7cocos2d8Director9drawSceneEv'), {
    onEnter() {
      for (const ui of scenes.values()) {
        if (ui.routing || (!ui.snap && !ui.dirty)) continue;
    if (ui.snap) {
      const t = Math.min(1, (Date.now() - ui.snap.time) / 180);
      ui.position = ui.snap.from + (ui.snap.to - ui.snap.from) * (1 - (1 - t) ** 3);
      if (t === 1) {
        ui.position = ui.snap.to; ui.snap = null;
        note('HOME_CAROUSEL_SETTLED position=' + ui.position);
      }
    }
        drawCarousel(ui);
      }
    }
  }));
  function dispatch(ui, card, touch, event) {
    if (!card.open) { note('HOME_LOCKED mode=' + card.name); return; }
    if (!card.owner) {
      if (card.name === 'Expedition') {
        // Original HomeScene::iconTouchEnded(19), after its availability gate.
        // The archived Home advertisement table is empty; its display lookup
        // cannot route this restored carousel entry. Keep the feature gate above
        // and reproduce the original request-owning connection scene instead.
        const next = allocate(0x600), request = allocate(0x30);
        expeditionCtor(next);
        expeditionRequestCtor(request);
        expeditionParam(next, request, 920000);
        changeStep(ui.scene, next, 0);
      }
      else changeScene(ui.scene, card.name === 'Craft' ? 1000 : 1100);
      note('HOME_CAROUSEL_OPEN mode=' + card.name);
      return;
    }
    ui.routing = true;
    route = {ui, index: ui.cards.indexOf(card), touch};
    try {
      // The original scene still picks and owns the touched sprite and runs
      // all retail unlock, capacity, story and event-resume checks. Only a
      // settled centre tap reaches it; a carousel drag never dispatches it.
      nativeBegin(ui.scene, touch, event);
      const picked = ui.scene.add(0x5d8).readPointer().equals(card.icon.node);
      const accepted = nativeEnd(ui.scene, touch, event);
      note('HOME_CAROUSEL_OPEN mode=' + card.name + ' picked=' + picked + ' accepted=' + accepted);
    } finally {
      route = null;
      ui.routing = false;
      if (scenes.get(ui.scene.toString()) === ui) draw(ui);
    }
  }
  return {
    begin(scene, touch) {
      const ui = scenes.get(scene.toString()), p = point(touch);
      if (!ui || !touchEnabled(scene) || !routeAllowed(scene)) return false;
      const direct = ui.cards.slice(6).find(c => hit(c.box, p));
      if (!direct && (p.y < ui.top || p.y > ui.bottomEdge)) return false;
      // All-at-once CANCEL may bypass the single-touch callback. Every
      // accepted DOWN starts fresh, even when Android reuses its Touch pointer.
      releasePress(ui);
      ui.snap = null;
      ui.gesture = {touch: touch.toString(), x: p.x, y: p.y, start: ui.position, direct};
      const card = direct || carouselHit(ui.carousel, p);
      const count = ui.carousel.length;
      const selected = ((Math.round(ui.position) % count) + count) % count;
      if (card && (direct || (ui.carousel.indexOf(card) === selected &&
          Math.abs(ui.position - Math.round(ui.position)) < 0.03))) press(ui, card);
      return true;
    },
    move(scene, touch) {
      const ui = scenes.get(scene.toString()), g = ui?.gesture;
      if (!g || g.touch !== touch.toString()) return;
      const p = point(touch);
      if (Math.abs(p.x - g.x) >= 14 || Math.abs(p.y - g.y) >= 14) releasePress(ui);
      if (g.direct) return;
      ui.position = g.start - (p.x - g.x) / (ui.width * 344 / 640);
      // Coalesce Android MOVE bursts into one update per rendered frame.
      ui.dirty = true;
    },
    end(scene, touch, event) {
      const ui = scenes.get(scene.toString()), g = ui?.gesture;
      if (!g || g.touch !== touch.toString()) return;
      ui.gesture = null;
      releasePress(ui);
      const p = point(touch), result = carouselRelease(g.start, p.x - g.x, ui.width);
      if (g.direct) {
        if (Math.abs(p.x - g.x) < 14 && Math.abs(p.y - g.y) < 14 && hit(g.direct.box, p))
          dispatch(ui, g.direct, touch, event);
        return;
      }
      if (result.dragged || Math.abs(p.y - g.y) >= 14) { snap(ui, result.position); return; }
      const card = carouselHit(ui.carousel, p);
      if (!card || !touchEnabled(scene)) { snap(ui, Math.round(ui.position)); return; }
      const count = ui.carousel.length, index = ui.carousel.indexOf(card);
      const selected = ((Math.round(ui.position) % count) + count) % count;
      if (index !== selected) { snap(ui, ui.position + carouselItems(ui.position, count, ui.width)[index].distance); return; }
      if (Math.abs(ui.position - Math.round(ui.position)) > 0.03) { snap(ui, Math.round(ui.position)); return; }
      dispatch(ui, card, touch, event);
    },
    cancel(scene) {
      const ui = scenes.get(scene.toString());
      if (ui) { releasePress(ui); ui.gesture = null; snap(ui, Math.round(ui.position)); }
    },
    leave(scene) {
      const ui = scenes.get(scene.toString());
      if (ui) dispose(ui);
      scenes.delete(scene.toString()); types.clear(); orbCounts.clear();
    }
  };
}
