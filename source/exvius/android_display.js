'use strict';

// Cocos FIXED_WIDTH/FIXED_HEIGHT expand the canvas with one uniform scale.
// SHOW_ALL preserves a fixed canvas and adds the bars seen on tall phones.
export function chooseResolution(width, height, frameWidth, frameHeight) {
  if (![width, height, frameWidth, frameHeight].every(value => Number.isFinite(value) && value > 0))
    return null;
  const fixedWidth = frameHeight / frameWidth >= height / width;
  const scale = fixedWidth ? frameWidth / width : frameHeight / height;
  return {
    policy: fixedWidth ? 4 : 3,
    width: fixedWidth ? width : Math.ceil(frameWidth / scale),
    height: fixedWidth ? Math.ceil(frameHeight / scale) : height,
    scale
  };
}

const FOOTER_GAP = 1136 - 1109;

export function clampAnimationFrame(frame, count) {
  return count > 0 && frame >= count ? count - 1 : frame;
}

// The visible clip, scroll limits and scrollbar are separate layout entries.
// Grow them together. Changing only the scroll limits leaves its old clip
// hiding the extra rows, as on Adventurer Crests and other lower-page lists.
export function isTallList(name, box, reference = {height: 1136}) {
  if (name.startsWith('home_') || /dialog|popup|tooltip/i.test(name)) return false;
  // The original Crests lists end at 909/911, above their separate note.
  // Their row mask is a different entry and must keep its 154px height.
  if (/^(?:clip_area|scrl_area|scrl_bar)_(?:wkreward|mthreward|mthtier)(?:_offset)?$/.test(name)) return true;
  if (!/clip|scroll|scrl|list/i.test(name) || box.height < reference.height * 0.25) return false;
  // A main-page viewport already ends near the footer. Embedded item and
  // results panels must keep room for their original action buttons below.
  return box.y < reference.height * 0.75 && box.y + box.height > reference.height * 0.84;
}

function isBottomLayout(name, box, reference) {
  return name.startsWith('parade_footer_') || name.startsWith('er_disclaimer_') ||
    ['party_register_list_slot_list_frame_bottom', 'party_register_list_caution_label',
     'party_register_list_bottom_frame'].includes(name) ||
    (name === 'shadow_bottom' && box.y >= reference.height * 0.7);
}

export function collapseCampaignBanner(name, box, original, banner, reference) {
  if (!banner || name.startsWith('footer_') || isBottomLayout(name, original, reference) ||
      (original.y < banner.y + banner.height - 1 && !name.startsWith('emblemtab_') && name !== 'bg_line')) return box;
  const result = {...box, y: box.y - banner.height};
  if (isTallList(name, original, reference)) result.height += banner.height;
  return result;
}

export function anchorLayout(name, box, reference, canvas) {
  const result = { ...box };
  const dy = canvas.height - reference.height;
  const dx = (canvas.width - reference.width) / 2;
  if (name.startsWith('footer_')) {
    // The 1136 layout leaves the menu (footer_bg ends at 1109) and its frame bar (footer_section_line
    // at 1100) above the design bottom; on the phone that was a black strip under Home. Seat both on the edge.
    result.x += dx;
    result.y += dy + (name === 'footer_section_line' ? reference.height - box.y : FOOTER_GAP);
    if (name === 'footer_bg' || name === 'footer_bg_gradation') {
      result.x = box.x;
      result.width += canvas.width - reference.width;
    }
  } else if (isTallList(name, box, reference)) {
    // Scroll lists authored to end above the 1136 footer (Bundles, Summon tabs) were cut off on tall
    // screens; they grow with the canvas down to the footer, which stays at the same distance above.
    result.height += dy;
  } else if (isBottomLayout(name, box, reference)) {
    result.x += dx;
    result.y += dy;
  } else if (name === 'unit_bg') {
    // Home loads this texture through BattleBgUtil, which ignores CSV size.
    // Its actual sprite is scaled uniformly after creation below.
  } else if (name === 'home_bg_clip_area') {
    result.width += canvas.width - reference.width;
    result.height += dy + FOOTER_GAP;
  } else if (name === 'menu_area' || name === 'info_bottom_bg_offset' ||
             name === 'home_bottom_parts_offset' || name === 'home_rotate_area' ||
             name === 'home_bg_gradation_bottom') {
    // Home's bottom parts move with the footer menu, keeping the authored spacing above it.
    result.x += dx;
    result.y += dy + FOOTER_GAP;
  }
  return result;
}

export function clampMapScroll(x, y, columns, rows, width, height) {
  if (![x, y, columns, rows, width, height].every(Number.isFinite) ||
      columns <= 0 || rows <= 0 || width <= 0 || height <= 0) return null;
  return {
    x: Math.max(0, Math.min(x, Math.max(0, columns * 58 - width))),
    y: Math.max(0, Math.min(y, Math.max(0, rows * 58 - height)))
  };
}

export function installAdaptiveDisplay(module, retained, note, bridge) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  // GL9 getMaxFrame returns the frame count. Its chest idle code passes that
  // count to inclusive getRandom, occasionally selecting one past the end.
  // setFrameNo only stores the integer as a float, without checking the bound.
  const animationFrames = native('_ZNK2ss6Player11getMaxFrameEv', 'int', ['pointer']);
  retained.push(Interceptor.attach(module.getExportByName('_ZN2ss6Player10setFrameNoEi'), {
    onEnter(args) {
      const frame = args[1].toInt32(), count = animationFrames(args[0]);
      const safe = clampAnimationFrame(frame, count);
      if (safe !== frame) {
        args[1] = ptr(safe);
        note('ANIMATION_FRAME_CLAMP frame=' + frame + ' count=' + count + ' safe=' + safe);
      }
    }
  }));
  // This GL9 build returns Size by value using a hidden C++ result register.
  // Read its two frame floats at the offsets verified in updateDesignResolutionSize.
  const getFrame = target => target.add(0x24);
  const getDesign = native('_ZNK7cocos2d6GLView23getDesignResolutionSizeEv', 'pointer', ['pointer']);
  const getScaleX = native('_ZNK7cocos2d6GLView9getScaleXEv', 'float', ['pointer']);
  const getScaleY = native('_ZNK7cocos2d6GLView9getScaleYEv', 'float', ['pointer']);
  const userState = native('_ZN9UserState6sharedEv', 'pointer', []);
  const nodeScaleX = native('_ZNK7cocos2d4Node9getScaleXEv', 'float', ['pointer']);
  const nodeScaleY = native('_ZNK7cocos2d4Node9getScaleYEv', 'float', ['pointer']);
  const nodeSize = native('_ZNK7cocos2d4Node14getContentSizeEv', 'pointer', ['pointer']);
  const nodeAnchor = native('_ZNK7cocos2d4Node14getAnchorPointEv', 'pointer', ['pointer']);
  const nodeX = native('_ZNK7cocos2d4Node12getPositionXEv', 'float', ['pointer']);
  const nodeY = native('_ZNK7cocos2d4Node12getPositionYEv', 'float', ['pointer']);
  const setScale = native('_ZN7cocos2d4Node8setScaleEff', 'void', ['pointer', 'float', 'float']);
  const setX = native('_ZN7cocos2d4Node12setPositionXEf', 'void', ['pointer', 'float']);
  const setY = native('_ZN7cocos2d4Node12setPositionYEf', 'void', ['pointer', 'float']);
  const mapColumns = native('_ZNK7MapData11getMapWidthEv', 'int', ['pointer']);
  const mapRows = native('_ZNK7MapData12getMapHeightEv', 'int', ['pointer']);
  const mapId = native('_ZNK7MapData8getMapIdEv', 'int', ['pointer']);
  const aliasTexture = native('_ZN7cocos2d9Texture2D21setAliasTexParametersEv', 'void', ['pointer']);
  let view = null;
  let layoutReady = false;
  let reference = { width: 640, height: 1136 };
  let canvas = { ...reference };
  let lastLayout = '';
  const originalBoxes = new Map();
  let footerLogged = false;
  let homeLayoutDepth = 0;
  let settingHomeBackground = false;
  let homeBackground = null;
  const emblemLayouts = [];
  const getLayout = native('_ZN15LayoutCacheList9getObjectERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEb',
    'pointer', ['pointer', 'pointer', 'bool']);
  const makeLayoutKey = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc',
    'void', ['pointer', 'pointer']);
  const freeLayoutKey = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev',
    'void', ['pointer']);
  const cast = new NativeFunction(Module.getGlobalExportByName('__dynamic_cast'),
    'pointer', ['pointer', 'pointer', 'pointer', 'long'], {exceptions: 'propagate'});
  const refType = module.getExportByName('_ZTIN7cocos2d3RefE');
  const monthlyType = module.getExportByName('_ZTI23sgUserEmblemMonthlyInfo');
  function emptyEmblemBanner(scene) {
    const array = scene.add(0x648).readPointer();
    if (array.isNull()) return null;
    const data = array.add(0x30).readPointer();
    if (data.isNull()) return null;
    const index = scene.add(0x640).readS16(), count = data.readU32();
    if (index < 0 || index >= count || count > 48) return null;
    const entries = data.add(0x10).readPointer(), entry = entries.add(index * Process.pointerSize).readPointer();
    if (entry.isNull()) return null;
    const info = cast(entry, refType, monthlyType, 0);
    if (info.isNull()) return null;
    const value = info.add(0x38), tag = value.readU8();
    const length = tag & 1 ? value.add(8).readU64().toNumber() : tag >>> 1;
    if (length !== 0) return null;
    const layouts = scene.add(0x430).readPointer();
    if (layouts.isNull()) return null;
    const key = Memory.alloc(24);
    const name = 'emblemreward_banner_offset';
    // Use the page's banner offset, not the image's local y=1 inside it.
    makeLayoutKey(key, Memory.allocUtf8String(name));
    let row;
    try { row = getLayout(layouts, key, 1); }
    finally { freeLayoutKey(key); }
    if (row.isNull()) return null;
    const original = originalBoxes.get(row.toString())?.box;
    const height = original ? original.height : row.add(0x30).readFloat();
    if (!(height > 0 && height < reference.height / 2)) return null;
    return {layouts, y: original ? original.y : row.add(0x28).readFloat(), height};
  }
  for (const name of ['_ZN18sgEmblemEventScene9setLayoutEv',
                     '_ZN18sgEmblemEventScene15setTabBtnLayoutEv',
                     '_ZN18sgEmblemEventScene18setTabDetailLayoutEv',
                     '_ZN18sgEmblemEventScene24setWeeklyMilestoneLayoutEv',
                     '_ZN18sgEmblemEventScene19setTierRewardLayoutEv'])
    retained.push(Interceptor.attach(module.getExportByName(name), {
      onEnter(args) {
        let banner = null;
        try { banner = emptyEmblemBanner(args[0]); }
        catch (error) { note('CREST_LAYOUT_DATA_ERROR ' + error); }
        emblemLayouts.push(banner);
      },
      onLeave() { emblemLayouts.pop(); }
    }));
  // An empty resource resolves to the engine's white placeholder texture.
  // With no campaign image, omit that sprite and reclaim its reserved space.
  let originalEmblemBanner;
  const emblemBanner = new NativeCallback(scene => {
    try { if (emptyEmblemBanner(scene)) return; }
    catch (error) { note('CREST_LAYOUT_DATA_ERROR ' + error); }
    originalEmblemBanner(scene);
  }, 'void', ['pointer']);
  originalEmblemBanner = new NativeFunction(Interceptor.replaceFast(
    module.getExportByName('_ZN18sgEmblemEventScene15setBannerLayoutEv'), emblemBanner), 'void', ['pointer'], {exceptions: 'propagate'});
  retained.push(emblemBanner);
  function updateContentRect() {
    if (!layoutReady || !view) return;
    const design = getDesign(view);
    const width = design.readFloat();
    const height = design.add(4).readFloat();
    if (!(width > 0 && height > 0)) return;
    canvas = { width, height };
    // GL9 initResolution stores the logical content rectangle at UserState+0x19c.
    // CommonUtils and native menu layout both read this same rectangle.
    const rect = userState().add(0x19c);
    rect.writeFloat(0);
    rect.add(4).writeFloat(0);
    rect.add(8).writeFloat(width);
    rect.add(12).writeFloat(height);
    const frame = getFrame(view);
    const sx = getScaleX(view);
    const sy = getScaleY(view);
    const layout = [frame.readFloat(), frame.add(4).readFloat(), width, height, sx, sy].join('x');
    if (layout !== lastLayout) {
      lastLayout = layout;
      note('ADAPTIVE_DISPLAY frame=' + frame.readFloat() + 'x' + frame.add(4).readFloat() +
        ' canvas=' + width + 'x' + height + ' scale=' + sx + ',' + sy);
    }
  }
  // Retire the game's simulated phone status strip. Android owns real insets.
  for (const name of ['_ZN11CommonUtils15isDrawStatusBarEv',
                       '_ZN11CommonUtils25adjustLayoutWithStatusBarEv']) {
    retained.push(Interceptor.attach(module.getExportByName(name), {
      onLeave(result) { result.replace(0); }
    }));
  }
  const address = module.getExportByName('_ZN7cocos2d6GLView23setDesignResolutionSizeEff16ResolutionPolicy');
  let original;
  const replacement = new NativeCallback(function (target, width, height, policy) {
    view = target;
    reference = { width, height };
    const frame = getFrame(target);
    const layout = chooseResolution(width, height, frame.readFloat(), frame.add(4).readFloat());
    original(target, width, height, layout ? layout.policy : policy);
  }, 'void', ['pointer', 'float', 'float', 'int']);
  retained.push(replacement);
  original = new NativeFunction(Interceptor.replaceFast(address, replacement),
    'void', ['pointer', 'float', 'float', 'int'], {exceptions: 'propagate'});
  retained.push(Interceptor.attach(module.getExportByName('_ZN7cocos2d6GLView26updateDesignResolutionSizeEv'), {
    onEnter(args) { this.view = args[0]; },
    onLeave() { view = this.view; updateContentRect(); }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN11AppDelegate14initResolutionEv'), {
    onLeave() { layoutReady = true; updateContentRect(); }
  }));
  // Returning to Title after a local loading failure can reset UserState's
  // content rectangle without recreating GLView. Reapply the live viewport
  // before the original title background and controls read that rectangle.
  const titleBackgrounds = [];
  const fillTitle = native('_ZN12GraphicUtils8fillRectEiffffRKN7cocos2d7Color3BEiib',
    'pointer', ['int', 'float', 'float', 'float', 'float', 'pointer', 'int', 'int', 'bool']);
  const titleBlack = Memory.alloc(3).writeByteArray([0, 0, 0]);
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11LayoutUtils23createGameSpriteByImageEPKcRKNSt6__ndk112basic_stringIcNS2_11char_traitsIcEENS2_9allocatorIcEEEEii'), {
    onEnter() {
      // TitleUtils uses this overload only for the configured custom title.
      if (titleBackgrounds.length) titleBackgrounds[titleBackgrounds.length - 1].custom = true;
    }
  }));
  for (const [name, mainTitle] of [
    ['_ZN10TitleUtils19setLayoutBackgroundEii', false],
    ['_ZN10TitleScene8setTitleEv', true]
  ]) retained.push(Interceptor.attach(module.getExportByName(name), {
    onEnter(args) {
      updateContentRect();
      // Main Title has its own background path, separate from TitleUtils'
      // auxiliary screens. Its pinned setTitle places art on layer 3.
      titleBackgrounds.push({layer: mainTitle ? 3 : args[0].toInt32(), custom: false});
    },
    onLeave() {
      const background = titleBackgrounds.pop();
      if (!background.custom) return;
      // The custom-art branch skips the original solid backdrop. Cover the
      // whole tall canvas behind the art instead of exposing its old white fill.
      fillTitle(background.layer, 0, 0, canvas.width, canvas.height, titleBlack, 0, 255, 0);
      note('TITLE_BACKGROUND_FILLED size=' + canvas.width + 'x' + canvas.height);
    }
  }));
  // Layout CSVs still contain coordinates for 960/1024/1136-high screens.
  // Move authored bottom controls as a group, including their touch rectangles.
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN15LayoutCacheList9getObjectERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEb'), {
    onEnter(args) {
      this.layouts = args[0];
      const text = args[1];
      const flag = text.readU8();
      const length = (flag & 1) ? text.add(8).readU64().toNumber() : flag >>> 1;
      this.name = length <= 256 ? ((flag & 1) ? text.add(16).readPointer() : text.add(1)).readUtf8String(length) : '';
    },
    onLeave(result) {
      if (!layoutReady || result.isNull() || !this.name) return;
      const name = this.name;
      if (['unit_bg', 'menu_area', 'info_bottom_bg_offset'].includes(name) && homeLayoutDepth === 0) return;
      const key = result.toString();
      let saved = originalBoxes.get(key);
      if (!saved || saved.name !== name) {
        saved = { name, box: {
          x: result.add(0x24).readFloat(), y: result.add(0x28).readFloat(),
          width: result.add(0x2c).readFloat(), height: result.add(0x30).readFloat()
        } };
        originalBoxes.set(key, saved);
      }
      const campaign = emblemLayouts.length ? emblemLayouts[emblemLayouts.length - 1] : null;
      const banner = campaign && campaign.layouts.equals(this.layouts) ? campaign : null;
      if (!banner && !name.startsWith('footer_') && !name.startsWith('home_') && !isTallList(name, saved.box, reference) &&
          !isBottomLayout(name, saved.box, reference) &&
          !['unit_bg', 'menu_area', 'info_bottom_bg_offset'].includes(name)) return;
      const box = collapseCampaignBanner(name, anchorLayout(name, saved.box, reference, canvas),
        saved.box, banner, reference);
      result.add(0x24).writeFloat(box.x);
      result.add(0x28).writeFloat(box.y);
      result.add(0x2c).writeFloat(box.width);
      result.add(0x30).writeFloat(box.height);
      if (!footerLogged && name === 'footer_home') {
        footerLogged = true;
        note('ADAPTIVE_FOOTER reference=' + reference.height + ' canvas=' + canvas.height +
          ' shift=' + (box.y - saved.box.y));
      }
    }
  }));
  // GL9's deleting destructor inlines D2 instead of calling it. Both paths
  // must discard saved geometry before another layout reuses the address.
  for (const name of ['_ZN11LayoutCacheD0Ev', '_ZN11LayoutCacheD2Ev'])
    retained.push(Interceptor.attach(module.getExportByName(name), {
      onEnter(args) { originalBoxes.delete(args[0].toString()); }
    }));
  // The screen frame is two header_DecoFrame sprites whose gold bar runs along the image's top edge:
  // UIHeader's at header_section_line, UIFooter's rotated 180 degrees at footer_section_line. The footer
  // layout puts its bar 36 units above the bottom of the 1136 design, which on taller screens left the bar
  // floating over the world map and a black strip under the Home menu (phone 2026-10-24). Each time a
  // scene sets a line, anchor its bar to the visible screen edge, from the view's own frame and scale
  // (cocos GLView::getVisibleOrigin/getVisibleSize: (design - frame / scale) / 2 for the fixed policies).
  const rotation = native('_ZNK7cocos2d4Node11getRotationEv', 'float', ['pointer']);
  function visibleEdges() {
    const design = getDesign(view).add(4).readFloat();
    const height = getFrame(view).add(4).readFloat() / getScaleY(view);
    const bottom = (design - height) / 2;
    return { bottom, top: bottom + height };
  }
  function anchorLine(line, edge) {
    // The bar is the image's top edge: (1 - anchorY) * height above the anchor, turned by the rotation.
    const height = nodeSize(line).add(4).readFloat() * nodeScaleY(line);
    const bar = (1 - nodeAnchor(line).add(4).readFloat()) * height * Math.cos(rotation(line) * Math.PI / 180);
    setY(line, visibleEdges()[edge] - bar);
  }
  for (const [name, field, edge] of [['_ZN8UIHeader14setSectionLineEi', 0x60, 'top'],
                                     ['_ZN8UIFooter14setSectionLineEi', 0xb8, 'bottom']]) {
    retained.push(Interceptor.attach(module.getExportByName(name), {
      onEnter(args) { this.self = args[0]; },
      onLeave() {
        const line = this.self.add(field).readPointer();
        if (line.isNull() || !view) return;
        anchorLine(line, edge);
      }
    }));
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN9HomeScene9setLayoutEv'), {
    onEnter() { homeLayoutDepth += 1; },
    onLeave() { homeLayoutDepth -= 1; }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE'), {
    onEnter(args) {
      if (settingHomeBackground && args[1].toInt32() === 2) homeBackground = args[3];
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN9HomeScene5setBgEv'), {
    onEnter() { settingHomeBackground = true; homeBackground = null; },
    onLeave() {
      settingHomeBackground = false;
      if (!homeBackground || homeBackground.isNull()) return;
      const node = homeBackground;
      const size = nodeSize(node), anchor = nodeAnchor(node);
      const sx = nodeScaleX(node), sy = nodeScaleY(node);
      const width = size.readFloat() * sx, height = size.add(4).readFloat() * sy;
      if (!(width > 0 && height > 0)) return;
      const scale = Math.max(1, canvas.width / width,
        (height + canvas.height - reference.height) / height);
      const x = nodeX(node) + (anchor.readFloat() - 0.5) * width * (scale - 1);
      const y = nodeY(node) + (anchor.add(4).readFloat() - 1) * height * (scale - 1);
      setScale(node, sx * scale, sy * scale);
      setX(node, x);
      setY(node, y);
      note('ADAPTIVE_HOME_BACKGROUND uniform=' + scale);
    }
  }));
  // The native upper bound becomes negative when an expanded viewport is
  // larger than a map. Clamp to the actual nonnegative map-scroll interval.
  const reportedMaps = new Set();
  const mapResources = new Map();
  let currentMapResource = '';
  const readMapResource = text => {
    const flag = text.readU8();
    const length = (flag & 1) ? text.add(8).readU64().toNumber() : flag >>> 1;
    if (length > 1024) return '';
    const value = ((flag & 1) ? text.add(16).readPointer() : text.add(1)).readUtf8String(length);
    return (value.match(/(?:^|[\\/])(?:Ver\d+_)?(\d{9})(?:\.cpk)?$/) || [])[1] || '';
  };
  // Global v9's map-reader wrapper selects the package before calling the
  // no-argument initMapData overload. That path bypasses the public string
  // overload below. Track the same original package selector in both paths.
  retained.push(Interceptor.attach(module.base.add(0x1f3913c), {
    onEnter(args) {
      const resource = readMapResource(args[1]);
      if (resource) currentMapResource = resource;
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN14MapDrawManager11initMapDataEv'), {
    onEnter(args) {
      if (currentMapResource) mapResources.set(args[0].toString(), currentMapResource);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN14MapDrawManager11initMapDataENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE'), {
    onEnter(args) {
      const resource = readMapResource(args[1]);
      if (resource) {
        currentMapResource = resource;
        mapResources.set(args[0].toString(), resource);
      }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN14MapDrawManager11updateLayerEv'), {
    onEnter(args) { this.manager = args[0]; },
    onLeave() {
      const manager = this.manager;
      const data = manager.add(0x2540).readPointer();
      if (data.isNull()) return;
      const width = manager.add(0x2568).readFloat();
      const height = manager.add(0x256c).readFloat();
      const columns = mapColumns(data), rows = mapRows(data);
      const x = manager.add(0x2558).readFloat(), y = manager.add(0x255c).readFloat();
      const resource = mapResources.get(manager.toString()) || '';
      const scroll = clampMapScroll(x, y, columns, rows, width, height);
      if (!scroll) return;
      manager.add(0x2558).writeFloat(scroll.x);
      manager.add(0x255c).writeFloat(scroll.y);
      const key = [data, mapId(data), columns, rows, width, height].join(':');
      if (!reportedMaps.has(key)) {
        reportedMaps.add(key);
        note('MAP_VIEWPORT resource=' + resource + ' id=' + mapId(data) +
          ' map=' + columns + 'x' + rows + ' window=' + width + 'x' + height +
          ' scroll=' + x + ',' + y + ' bounded=' + scroll.x + ',' + scroll.y);
      }
    }
  }));
  // The archive reader returns 32px fallback textures for Mitra's first two
  // atlases even though their original 986px PNGs are present in the package.
  // Load whole, byte-identical original images through the proven file loader.
  const textureWidth = native('_ZNK7cocos2d9Texture2D13getPixelsWideEv', 'int', ['pointer']);
  const director = native('_ZN7cocos2d8Director11getInstanceEv', 'pointer', []);
  const textureCache = native('_ZNK7cocos2d8Director15getTextureCacheEv', 'pointer', ['pointer']);
  const addImage = native('_ZN7cocos2d12TextureCache8addImageERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE',
    'pointer', ['pointer', 'pointer']);
  const makeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc',
    'void', ['pointer', 'pointer']);
  const freeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev', 'void', ['pointer']);
  const replaceTexture = native('_ZN7cocos2d7__Array20replaceObjectAtIndexElPNS_3RefEb',
    'void', ['pointer', 'int64', 'pointer', 'bool']);
  const mapTexture = (manager, index) => manager.add(0x2548).readPointer().add(0x30)
    .readPointer().add(0x10).readPointer().add(index * Process.pointerSize).readPointer();
  retained.push(Interceptor.attach(module.getExportByName('_ZN14MapDrawManager11loadMapDataEi'), {
    onEnter(args) {
      const manager = args[0], resource = mapResources.get(manager.toString());
      if (resource !== '111020100') return;
      const begin = manager.add(0x28).readPointer();
      const count = manager.add(0x30).readPointer().sub(begin).toInt32() / 4;
      if (count < 1 || count > 128) return;
      for (let i = 0; i < count; i++) {
        const id = begin.add(i * 4).readS32();
        if (id !== 20010 && id !== 20011) continue;
        const texture = mapTexture(manager, i);
        if (!texture.isNull() && textureWidth(texture) >= 58) continue;
        const filename = 'mapchip_0003_00' + (id - 20009) + '.png';
        try {
          const relative = '/common_lang/sd/map/11/' + resource + '/' + filename;
          const path = bridge('materializedPath', '(Ljava/lang/String;)Ljava/lang/String;', [relative]);
          if (!path) continue;
          const value = Memory.alloc(24);
          makeString(value, Memory.allocUtf8String(path));
          let replacement;
          try { replacement = addImage(textureCache(director()), value); }
          finally { freeString(value); }
          if (replacement.isNull() || textureWidth(replacement) !== 986) continue;
          aliasTexture(replacement);
          replaceTexture(manager.add(0x2548).readPointer(), i, replacement, 1);
          note('MAP_ATLAS_RECOVERED resource=' + resource + ' image=' + filename + ' width=986');
        } catch (error) { note('MAP_ATLAS_RECOVERY_ERROR ' + error); }
      }
    }
  }));
  // MapDrawManager already uses nearest-neighbour sampling for its pixel-art
  // tiles. AreaMapManager omitted it for the separate World/region sheets,
  // allowing linear sampling across sheet edges at fractional phone scales.
  let areaMapDepth = 0;
  retained.push(Interceptor.attach(module.getExportByName('_ZN14AreaMapManager16setLayoutAreaMapEP9GameScene'), {
    onEnter() { areaMapDepth += 1; },
    onLeave() { areaMapDepth -= 1; }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN10GameSprite4initEPN7cocos2d9Texture2DE'), {
    onEnter(args) {
      if (areaMapDepth && !args[1].isNull()) aliasTexture(args[1]);
    }
  }));
}

// Movie geometry only. Metadata arrives once when the existing CRI renderer opens a movie.
export function fitMovie(bounds, sourceWidth, sourceHeight) {
  if (![bounds.width, bounds.height, sourceWidth, sourceHeight].every(v => Number.isFinite(v) && v > 0))
    return null;
  const scale = Math.min(bounds.width / sourceWidth, bounds.height / sourceHeight);
  return {...bounds, width: sourceWidth * scale, height: sourceHeight * scale};
}

export function installMovieAspectFit(module, retained, note) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args);
  const handle = native('_ZN10cricocos2d4mana6Sprite15getManaPlayerHnEv', 'pointer', ['pointer']);
  const quadName = '_ZN10cricocos2d4mana6Sprite15setQuadVerticesERKN7cocos2d4RectE';
  const setQuad = native(quadName, 'void', ['pointer', 'pointer']);
  const movies = new Map();
  let applying = false;
  function rectangle(value) {
    const result = Memory.alloc(16);
    [value.x, value.y, value.width, value.height].forEach((v, i) => result.add(i * 4).writeFloat(v));
    return result;
  }
  function fitted(movie) {
    return movie.bounds && movie.source && fitMovie(movie.bounds, movie.source.width, movie.source.height);
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN10cricocos2d4mana6Sprite16createWithPlayerEv'), {
    onLeave(sprite) {
      if (sprite.isNull()) return;
      const node = ptr(sprite.toString());
      const player = handle(node);
      if (player.isNull()) return;
      const movie = {sprite: node, player, bounds: null, source: null};
      movies.set('sprite:' + node, movie);
      movies.set('player:' + player, movie);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(quadName), {
    onEnter(args) {
      if (applying) return;
      const movie = movies.get('sprite:' + args[0]);
      if (!movie) return;
      movie.bounds = {x: args[1].readFloat(), y: args[1].add(4).readFloat(),
        width: args[1].add(8).readFloat(), height: args[1].add(12).readFloat()};
      const fit = fitted(movie);
      if (fit) { this.rectangle = rectangle(fit); args[1] = this.rectangle; }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN10cricocos2d4mana6detail26RendererResourceFactorySet20createRenderResourceERK16CriManaMovieInfoP16CriManaPlayerTag'), {
    onEnter(args) {
      const movie = movies.get('player:' + args[2]);
      if (!movie) return;
      // First video stream width/height in the pinned GL9 CriManaMovieInfo layout.
      movie.source = {width: args[1].add(20).readU32(), height: args[1].add(24).readU32()};
      const fit = fitted(movie);
      if (!fit) return;
      applying = true;
      try { setQuad(movie.sprite, rectangle(fit)); }
      finally { applying = false; }
      note('MOVIE_ASPECT_FIT source=' + movie.source.width + 'x' + movie.source.height +
        ' viewport=' + movie.bounds.width + 'x' + movie.bounds.height + ' fitted=' + fit.width + 'x' + fit.height);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN10cricocos2d4mana6SpriteD1Ev'), {
    onEnter(args) {
      const movie = movies.get('sprite:' + args[0]);
      if (!movie) return;
      movies.delete('sprite:' + movie.sprite);
      movies.delete('player:' + movie.player);
    }
  }));
}
