import eventArt from '../server/event_art.json';
import raidArchive from '../server/raid_archive.json';
import colosseumNames from '../server/colosseum_names.json';
import battleNames from '../server/battle_names.json';
import exbonusText from '../server/content/exbonus_text.json';

// GateScene does not queue image downloads. Supply the original event banners
// from the bundled overlay and retain the native reader for other textures.
export function installMenuAssets(module, note, retained, bridge, modeChooserName = () => null) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const manager = new NativeFunction(module.base.add(0x1f38ef8), 'pointer', [], {exceptions: 'propagate'});
  const fileLoader = new NativeFunction(module.base.add(0x1f39004), 'pointer', ['pointer'], {exceptions: 'propagate'});
  const indexedImage = new NativeFunction(module.base.add(0x1f3a120), 'bool',
    ['pointer', 'pointer'], {exceptions: 'propagate'});
  const director = native('_ZN7cocos2d8Director11getInstanceEv', 'pointer', []);
  const textureCache = native('_ZNK7cocos2d8Director15getTextureCacheEv', 'pointer', ['pointer']);
  const addImage = native('_ZN7cocos2d12TextureCache8addImageERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE',
    'pointer', ['pointer', 'pointer']);
  const constructString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc',
    'void', ['pointer', 'pointer']);
  const destroyString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev',
    'void', ['pointer']);
  const gateCondition = native('_ZN8GateUtil29getSpDungeonCondMstWithAreaIdEib', 'pointer', ['int', 'bool']);
  function stringValue(value) {
    const flags = value.readU8();
    const length = (flags & 1) ? value.add(8).readU64().toNumber() : flags >>> 1;
    return length <= 512 ? ((flags & 1) ? value.add(16).readPointer() : value.add(1)).readUtf8String(length) : '<invalid>';
  }
  // The stock ranking preview adds its leader texture unconditionally for
  // every unit. Keep the original first-slot badge and hide later copies.
  let rankingSlot = -1;
  const spriteVisible = native('_ZN7cocos2d4Node10setVisibleEb', 'void', ['pointer', 'bool']);
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN15TfaRankingScene17setLayoutUserUnitEiRNSt6__ndk16vectorIiNS0_9allocatorIiEEEES5_ii'), {
    onEnter(args) { this.previous = rankingSlot; rankingSlot = args[1].toInt32(); },
    onLeave() { rankingSlot = this.previous; }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11LayoutUtils33createGameSpriteBySpriteFrameNameEPN7cocos2d15SpriteBatchNodeERKNSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEEffffiRKNS0_4Vec2E'), {
    onEnter(args) { this.hide = rankingSlot > 0 && stringValue(args[1]) === 'unit_chara_label_leader.png'; },
    onLeave(result) { if (this.hide && !result.isNull()) spriteVisible(result, 0); }
  }));
  // No selected options need no extra panel. The original empty panel puts
  // its heading over the fixed header; retain the normal populated renderer.
  const rankingGambits = native('_ZN14TfaRankingInfo13getGambitInfoEv', 'pointer', ['pointer']);
  const gambitAddress = module.getExportByName(
    '_ZN15TfaRankingScene15setLayoutGambitEP14TfaRankingInfoRiiPN7cocos2d15SpriteBatchNodeES5_S5_S5_S5_');
  const gambitArgs = ['pointer', 'pointer', 'pointer', 'int', 'pointer', 'pointer', 'pointer', 'pointer', 'pointer'];
  let originalGambit;
  const layoutGambit = new NativeCallback(function (scene, info, cursor, layer, a, b, c, d, e) {
    if (!info.isNull()) {
      const selected = rankingGambits(info);
      const end = selected.add(8).readPointer();
      let populated = false;
      for (let item = selected.readPointer(); item.compare(end) < 0; item = item.add(4))
        if (item.readS32() > 0) { populated = true; break; }
      if (!populated) return;
    }
    originalGambit(scene, info, cursor, layer, a, b, c, d, e);
  }, 'void', gambitArgs);
  originalGambit = new NativeFunction(Interceptor.replaceFast(gambitAddress, layoutGambit),
    'void', gambitArgs, {exceptions: 'propagate'});
  retained.push(layoutGambit, originalGambit);
  // The recovered map's own English table names Mitra correctly, but the
  // party menu's map-script lookup still returns its enum fallback. Fill only
  // this proven missing entry in the owned result using native assignment.
  const assignString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6assignEPKcm',
    'pointer', ['pointer', 'pointer', 'uint64']);
  for (const method of ['getMstText', 'getText']) retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11TextManager' + method.length + method + 'ERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE'), {
    onEnter(args) {
      this.key = stringValue(args[1]);
      this.name = this.key === 'MST_DUNGEONS_NAME_99999' ? 'Story' :
        this.key.startsWith('MST_ABILITY_NAME_') ? exbonusText[this.key.slice(17)]?.name :
        this.key.startsWith('MST_ABILITY_EXPLAIN_SHORT_') ? exbonusText[this.key.slice('MST_ABILITY_EXPLAIN_SHORT_'.length)]?.description :
        this.key.startsWith('MST_ABILITY_SHORTDESCRIPTION_') ? exbonusText[this.key.slice('MST_ABILITY_SHORTDESCRIPTION_'.length)]?.description :
        this.key.startsWith('MST_ABILITY_LONGDESCRIPTION_') ? exbonusText[this.key.slice('MST_ABILITY_LONGDESCRIPTION_'.length)]?.description :
        this.key.startsWith('MST_MONSTER_SKILL_NAME_') ? battleNames.skill[this.key.slice(23)] :
        this.key.startsWith('MST_MONSTER_NAME_') ? (battleNames.monster[this.key.slice(17)] || colosseumNames[this.key.slice(17)]) : null;
    },
    onLeave(result) {
      // GL9 returns a reference to its cached std::string in x0, not a
      // by-value string in x8. Fill only a known reconstruction's missing
      // native label; existing original translations remain authoritative.
      if (this.name && !result.isNull()) {
        const value = stringValue(result);
        if (!value || value === this.key || /^TFA\b/.test(value) || /[\u3040-\u30ff\u3400-\u9fff]/.test(value))
          assignString(result, Memory.allocUtf8String(this.name), Array.from(this.name).reduce((n, c) =>
            n + (c.codePointAt(0) < 128 ? 1 : c.codePointAt(0) < 2048 ? 2 : c.codePointAt(0) < 65536 ? 3 : 4), 0));
      }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11TextManager16getMapScriptTextENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE'), {
    onEnter(args) {
      const key = stringValue(args[1]);
      if (key === '120064' || key === 'MAP_TEXT_120064') this.out = this.context.x8;
    },
    onLeave() {
      const result = this.out;
      if (!result || result.isNull() || stringValue(result) !== 'MAP_TEXT_120064') return;
      const text = 'Town of Mitra';
      assignString(result, Memory.allocUtf8String(text), text.length);
      note('LOCAL_TOWN_TEXT_RECOVERED key=MAP_TEXT_120064');
    }
  }));
  const owned = new Set(Object.values(eventArt.events).flatMap(event => [event.filename, event.menu_background].filter(Boolean)));
  for (const event of raidArchive.events) if (event.menu_background) owned.add(event.menu_background);
  const managed = new Set(owned);
  const nestedImages = new Map(), fallbackImages = new Set(), dungeonScenes = [];
  let checkingInnerImage = false;
  // Retain the original image strings for list modes that use them directly.
  // Mode 3 resolves a separate icon below, rather than DungeonMst::getImageInfo.
  for (const [dungeon, original] of Object.entries(eventArt.dungeons || {})) {
    const info = {...original, dungeon};
    if (!info.original_image) continue;
    nestedImages.set(info.original_image, info);
    managed.add(info.original_image);
  }
  const dungeonIconCaller = module.base.add(0x219e1b8);
  let innerIconReports = 0;
  retained.push(Interceptor.attach(module.getExportByName('_ZN11IconMstList11getFileNameEi'), {
    onEnter() {
      // GL9's mode-3 list looks up DungeonMst+0x40 in IconMstList at
      // 0x219e1b4. Its checked DungeonMst pointer is kept in x24. Other icon
      // lookups in this scene are rewards and must retain their normal paths.
      if (!dungeonScenes.length || !this.returnAddress.equals(dungeonIconCaller)) return;
      const dungeon = this.context.x24;
      if (dungeon.isNull()) return;
      this.id = dungeon.add(0x24).readS32();
      const info = eventArt.dungeons?.[String(this.id)];
      this.info = info ? {...info, dungeon: String(this.id)} : null;
      this.output = this.context.x8;
    },
    onLeave() {
      if (!this.info) return;
      let name = stringValue(this.output);
      if (name === '<invalid>') return;
      let available = false;
      if (name && name !== 'spd_bn_dummy.png') {
        checkingInnerImage = true;
        try { available = indexedImage(manager(), this.output); }
        finally { checkingInnerImage = false; }
      }
      if (!available) {
        // Original map-icon names are shared by unrelated campaigns. Give
        // each fallback its own batch key so a cached banner cannot leak
        // from the previously visited event into the next one.
        name = 'local_dungeon_' + this.id + '.png';
        assignString(this.output, Memory.allocUtf8String(name), name.length);
      }
      nestedImages.set(name, this.info);
      managed.add(name);
      if (innerIconReports++ < 12) note('LOCAL_INNER_ICON dungeon=' + this.id + ' name=' + name);
    }
  }));
  let conditionReported = false;
  let reports = 0;
  let depth = 0;
  let supplying = false;
  const attached = new Set();
  const unavailable = new Set();
  const localPaths = new Map();
  const raidPictures = [];
  const raidMenuImages = new Set(raidArchive.events.map(event => event.menu_background).filter(Boolean));
  let areaDirectory = '';
  // GateScene checks the archive index before asking the texture reader. The
  // managed PNGs live in the local overlay rather than the original archives.
  retained.push(Interceptor.attach(module.base.add(0x1f3a120), {
    onEnter(args) {
      if (!checkingInnerImage && depth && managed.has(stringValue(args[1]))) this.managed = true;
    },
    onLeave(result) { if (this.managed) result.replace(1); }
  }));
  retained.push(Interceptor.attach(module.base.add(0x1ef2df0), {
    onEnter(args) {
      // The raid background's manager first checks CRI's C-string index
      // directly, bypassing the std::string wrapper above. Let the same
      // owned files reach its existing texture reader on this path too.
      if (!checkingInnerImage && depth && !args[1].isNull() &&
          managed.has(args[1].readUtf8String())) this.managed = true;
    },
    onLeave(result) { if (this.managed) result.replace(1); }
  }));
  function attachTextureReader() {
    const loader = fileLoader(manager());
    if (loader.isNull()) return;
    // LayoutUtils calls this vtable entry with (loader, image filename) and
    // passes its Texture2D return directly to SpriteBatchNode::createWithTexture.
    const address = loader.readPointer().add(0x30).readPointer();
    const key = address.toString();
    if (attached.has(key)) return;
    attached.add(key);
    note('LOCAL_MENU_READER_READY address=' + address.sub(module.base));
    function supply(original) {
        supplying = true;
        const filename = nestedImages.get(original)?.filename || original;
        if (raidPictures.length && owned.has(original))
          raidPictures[raidPictures.length - 1].archived = true;
        let stage = 'path';
        try {
          // All owned event images are installed together. Resolve their
          // directory once, rather than crossing JNI for every banner in a
          // 625-campaign list while Android is collecting native callback roots.
          const path = localPaths.get(filename) || (owned.has(filename) && areaDirectory ?
            areaDirectory + filename : bridge('materializedPath', '(Ljava/lang/String;)Ljava/lang/String;',
              ['/en/sd/area/' + filename]));
          if (!path) {
            unavailable.add(filename);
            note('LOCAL_MENU_IMAGE_UNAVAILABLE name=' + filename);
            return ptr(0);
          }
          localPaths.set(filename, path);
          if (owned.has(filename) && path.endsWith('/' + filename))
            areaDirectory = path.slice(0, -filename.length);
          stage = 'native-string';
          const value = Memory.alloc(24);
          constructString(value, Memory.allocUtf8String(path));
          let texture;
          try { stage = 'texture'; texture = addImage(textureCache(director()), value); }
          finally { destroyString(value); }
          if (!texture.isNull()) {
            if (nestedImages.has(original)) fallbackImages.add(original);
            note('LOCAL_MENU_IMAGE_SUPPLIED name=' + filename);
          }
          return texture;
        } catch (error) {
          note('LOCAL_MENU_IMAGE_ERROR name=' + filename + ' stage=' + stage + ' ' + error);
        } finally {
          supplying = false;
        }
        return ptr(0);
    }
    let originalReader;
    const reader = new NativeCallback((loader, filename) => {
      if (!depth || supplying || filename.isNull()) return originalReader(loader, filename);
      const name = filename.readUtf8String();
      if (reports++ < 24) note('LOCAL_MENU_IMAGE_READ name=' + name);
      if (!/^[A-Za-z0-9_.-]+\.(?:png|jpe?g)$/i.test(name) || unavailable.has(name))
        return originalReader(loader, filename);
      // These archive banners are owned overlay files. Do not first ask CRI
      // to load an absent file and enter its Java error-reporting path.
      if (owned.has(name)) return supply(name);
      const result = originalReader(loader, filename);
      return result.isNull() ? supply(name) : result;
    }, 'pointer', ['pointer', 'pointer']);
    originalReader = new NativeFunction(Interceptor.replaceFast(address, reader),
      'pointer', ['pointer', 'pointer'], {exceptions: 'propagate'});
    retained.push(reader);
  }
  const parentOf = native('_ZNK7cocos2d4Node9getParentEv', 'pointer', ['pointer']);
  const sizeOf = native('_ZNK7cocos2d4Node14getContentSizeEv', 'pointer', ['pointer']);
  const anchorOf = native('_ZNK7cocos2d4Node14getAnchorPointEv', 'pointer', ['pointer']);
  const xOf = native('_ZNK7cocos2d4Node12getPositionXEv', 'float', ['pointer']);
  const yOf = native('_ZNK7cocos2d4Node12getPositionYEv', 'float', ['pointer']);
  const scaleXOf = native('_ZNK7cocos2d4Node9getScaleXEv', 'float', ['pointer']);
  const scaleYOf = native('_ZNK7cocos2d4Node9getScaleYEv', 'float', ['pointer']);
  const zOf = native('_ZNK7cocos2d4Node14getLocalZOrderEv', 'int', ['pointer']);
  const addNode = native('_ZN7cocos2d4Node8addChildEPS0_ii', 'void', ['pointer', 'pointer', 'int', 'int']);
  const position = native('_ZN7cocos2d4Node11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const anchor = native('_ZN7cocos2d4Node14setAnchorPointERKNS_4Vec2E', 'void', ['pointer', 'pointer']);
  const removeNode = native('_ZN7cocos2d4Node26removeFromParentAndCleanupEb', 'void', ['pointer', 'bool']);
  const retain = native('_ZN7cocos2d3Ref6retainEv', 'void', ['pointer']);
  const release = native('_ZN7cocos2d3Ref7releaseEv', 'void', ['pointer']);
  const dimensions = native('_ZN7cocos2d5Label13setDimensionsEff', 'void', ['pointer', 'float', 'float']);
  const makeLabel = native('_ZN9GameScene14setStringLabelEiRKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEffRKN7cocos2d7Color3BEiii',
    'pointer', ['pointer', 'int', 'pointer', 'float', 'float', 'pointer', 'int', 'int', 'int']);
  const makeStrip = native('_ZN7cocos2d10LayerColor6createERKNS_7Color4BEff',
    'pointer', ['pointer', 'float', 'float']);
  const white = Memory.alloc(3).writeByteArray([255, 255, 255]);
  const dark = Memory.alloc(4).writeByteArray([0, 12, 30, 205]);
  const zero = Memory.alloc(8).writeByteArray(new Uint8Array(8));
  const middle = Memory.alloc(8).writeFloat(0.5);
  middle.add(4).writeFloat(0.5);
  const setScale = native('_ZN7cocos2d4Node8setScaleEff', 'void', ['pointer', 'float', 'float']);
  retained.push(Interceptor.attach(module.getExportByName('_ZN10GameSprite4initEPN7cocos2d9Texture2DE'), {
    onEnter() {
      // This is GL9's raid-background factory call, returning a GameSprite*.
      this.raid = raidPictures.length && this.returnAddress.equals(module.base.add(0x21ac850)) ?
        raidPictures[raidPictures.length - 1] : null;
    },
    onLeave(result) {
      if (this.raid && !result.isNull()) this.raid.image = ptr(result.toString());
    }
  }));
  const nestedBatches = new Map();
  let innerBatchReports = 0;
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEP13CriFileLoaderiij'), {
    onEnter(args) {
      if (dungeonScenes.length) {
        this.name = stringValue(args[0]);
        if (innerBatchReports++ < 12) note('LOCAL_INNER_BATCH name=' + this.name + ' mapped=' + nestedImages.has(this.name));
      }
    },
    onLeave(batch) {
      if (this.name && nestedImages.has(this.name) && !batch.isNull())
        nestedBatches.set(batch.toString(), this.name);
      else if (!batch.isNull()) nestedBatches.delete(batch.toString());
    }
  }));
  function caption(image, name, info, scene, imageLayer) {
      if (!info || image.isNull()) return;
      const modeName = modeChooserName(info.dungeon);
      if (!modeName && !fallbackImages.has(name)) return;
      try {
        const batch = parentOf(image);
        if (batch.isNull()) return;
        // SpriteBatchNode accepts only sprites using its own texture. Put the
        // text and tint beside that batch in the same clipped scroll layer.
        const parent = parentOf(batch);
        if (parent.isNull()) return;
        const size = sizeOf(image), point = anchorOf(image);
        const sx = scaleXOf(batch), sy = scaleYOf(batch);
        const width = size.readFloat() * Math.abs(scaleXOf(image) * sx);
        const height = size.add(4).readFloat() * Math.abs(scaleYOf(image) * sy);
        if (width < 100 || height < 42) return;
        const left = xOf(batch) + xOf(image) * sx - width * point.readFloat();
        const bottom = yOf(batch) + yOf(image) * sy - height * point.add(4).readFloat(), z = zOf(batch);
        const strip = makeStrip(dark, width, 42);
        position(strip, left, bottom);
        addNode(parent, strip, z + 1, -56000);
        const text = Memory.alloc(24);
        constructString(text, Memory.allocUtf8String(modeName || info.name));
        let label;
        try { label = makeLabel(scene, imageLayer, text, 0, 0, white, 1, 17, z + 2); }
        finally { destroyString(text); }
        if (label.isNull()) return;
        retain(label);
        removeNode(label, 0);
        dimensions(label, width - 20, 38);
        anchor(label, zero);
        position(label, left + 10, bottom + 2);
        addNode(parent, label, z + 2, -56001);
        release(label);
      } catch (error) { note('LOCAL_INNER_BANNER_CAPTION_ERROR ' + error); }
  }
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11LayoutUtils23createGameSpriteByImageEPN7cocos2d15SpriteBatchNodeEffRKNS0_4Vec2E'), {
    onEnter(args) {
      if (!dungeonScenes.length) return;
      this.name = nestedBatches.get(args[0].toString());
      this.info = nestedImages.get(this.name);
      this.scene = dungeonScenes[dungeonScenes.length - 1];
    },
    onLeave(image) { caption(image, this.name, this.info, this.scene, 2); }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN11LayoutUtils23createGameSpriteByImageEPKciffffiRKN7cocos2d4Vec2E'), {
    onEnter(args) {
      if (!dungeonScenes.length || args[0].isNull()) return;
      this.name = args[0].readUtf8String();
      this.info = nestedImages.get(this.name);
      this.scene = dungeonScenes[dungeonScenes.length - 1];
      this.layer = args[1].toInt32();
    },
    onLeave(image) {
      caption(image, this.name, this.info, this.scene, this.layer);
    }
  }));
  for (const name of [
    '_ZN9GateScene10initializeEv',
    '_ZN9GateScene13setListLayoutEbiN7cocos2d4Vec2E',
    '_ZN16GateDungeonScene10initializeEv',
    '_ZN16GateDungeonScene13setListLayoutEv',
    '_ZN16GateMissionScene10initializeEv',
    '_ZN16GateMissionScene13setLayoutRaidEv',
    '_ZN15ParadeAreaScene10initializeEv',
    '_ZN18ParadeDungeonScene10initializeEv',
    '_ZN16ParadeEntryScene10initializeEv',
    '_ZN26ParadeReadyForMissionScene10initializeEv',
    '_ZN11TfaTopScene19setLayoutBannerInfoEv'
  ]) retained.push(Interceptor.attach(module.getExportByName(name), {
    onEnter(args) {
      depth += 1;
      this.dungeon = name.includes('GateDungeonScene');
      this.raid = name === '_ZN16GateMissionScene13setLayoutRaidEv';
      if (this.raid) raidPictures.push({});
      if (this.dungeon) dungeonScenes.push(args[0]);
      attachTextureReader();
      if (!conditionReported) {
        conditionReported = true;
        for (const id of [734, 888, 970]) {
          try {
            const info = gateCondition(id, 1);
            note('LOCAL_GATE_CONDITION area=' + id + (info.isNull() ? ' missing' :
              ' image=' + stringValue(info.add(0xa0)) + ' raid=' + info.add(0x170).readS32() +
              ' start=' + info.add(0x58).readS64() + ' end=' + info.add(0x60).readS64()));
          } catch (error) { note('LOCAL_GATE_CONDITION_ERROR area=' + id + ' ' + error); }
        }
      }
    },
    onLeave() {
      if (this.raid) {
        const picture = raidPictures.pop();
        if (picture.archived && picture.image) {
          const image = picture.image, size = sizeOf(image), point = anchorOf(image);
          const width = size.readFloat(), height = size.add(4).readFloat();
          if (width > 0 && height > 0) {
            const centerY = yOf(image) + (0.5 - point.add(4).readFloat()) * height * scaleYOf(image);
            // Recovered campaign art is a banner, not the original text-free
            // backdrop. Fit it beside the timer and below the orbs so its
            // lettering cannot sit underneath the native level/HP labels.
            const scale = Math.min(300 / width, 88 / height);
            anchor(image, middle);
            setScale(image, scale, scale);
            position(image, 440, centerY - 8);
            note('LOCAL_RAID_BANNER_FITTED size=' + width + 'x' + height);
          }
        }
      }
      if (this.dungeon) dungeonScenes.pop();
      depth -= 1;
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN16GateMissionScene19setSelectDungeonMstEP10DungeonMstP7AreaMst'), {
    onEnter(args) {
      if (!args[1].isNull()) note('LOCAL_GATE_DUNGEON id=' + args[1].add(0x24).readS32());
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN16GateDungeonScene16setSelectAreaMstEP7AreaMst'), {
    onEnter(args) { if (!args[1].isNull()) note('LOCAL_GATE_SELECTED area=' + args[1].add(0x88).readS32()); }
  }));
}
