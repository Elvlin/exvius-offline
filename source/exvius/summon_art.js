import artwork from '../server/summon_art.json';

export function fitSummonArt(sourceWidth, sourceHeight, width, height) {
  if (![sourceWidth, sourceHeight, width, height].every(n => Number.isFinite(n) && n > 0)) return null;
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  return {width: sourceWidth * scale, height: sourceHeight * scale};
}

// GL9's image carousel stretches every source to its layout rectangle. Use
// the original wide variant where available, then fit the complete image
// proportionally. Both source artwork and native carousel controls stay intact.
export function installSummonArt(module, note, retained, bridge) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const makeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc',
    'void', ['pointer', 'pointer']);
  const freeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev',
    'void', ['pointer']);
  const getBanner = native('_ZNK18GachaDetailScrlObj9getBannerEv', 'pointer', ['pointer']);
  const anchor = native('_ZNK7cocos2d4Node14getAnchorPointEv', 'pointer', ['pointer']);
  const getX = native('_ZNK7cocos2d4Node12getPositionXEv', 'float', ['pointer']);
  const getY = native('_ZNK7cocos2d4Node12getPositionYEv', 'float', ['pointer']);
  const setX = native('_ZN7cocos2d4Node12setPositionXEf', 'void', ['pointer', 'float']);
  const setY = native('_ZN7cocos2d4Node12setPositionYEf', 'void', ['pointer', 'float']);
  let currentObject = null, reports = 0;
  const offsets = new Map();
  function center(object) {
    const box = offsets.get(object.toString());
    if (!box) return;
    const node = getBanner(object);
    if (node.isNull()) return;
    const x = getX(node), y = getY(node);
    if (box.adjusted && Math.abs(x - box.adjusted.x) < 0.01 && Math.abs(y - box.adjusted.y) < 0.01) return;
    const point = anchor(node);
    box.adjusted = {x: x + (0.5 - point.readFloat()) * box.dx,
                    y: y + (0.5 - point.add(4).readFloat()) * box.dy};
    setX(node, box.adjusted.x);
    setY(node, box.adjusted.y);
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObj9addObjectEiff'), {
    onEnter(args) {
      this.previous = currentObject;
      this.object = currentObject = args[0];
      offsets.delete(this.object.toString());
    },
    onLeave() { center(this.object); currentObject = this.previous; }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObj14updatePositionEff'), {
    onEnter(args) { this.object = args[0]; },
    onLeave() { center(this.object); }
  }));
  retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObjD1Ev'), {
    onEnter(args) { offsets.delete(args[0].toString()); }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN21GachaBannerDownloader12createBannerERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEERKN7cocos2d4SizeE'), {
    onEnter(args) {
      const flags = args[0].readU8();
      const length = flags & 1 ? args[0].add(8).readU64().toNumber() : flags >>> 1;
      if (length > 1024) return;
      let path = (flags & 1 ? args[0].add(16).readPointer() : args[0].add(1)).readUtf8String(length);
      let name = path.split(/[\\/]/).pop(), size = artwork.images[name];
      if (!size) return;
      let width = args[1].readFloat(), height = args[1].add(4).readFloat();
      if (width <= 0 || height <= 0) {
        if (size[0] <= 640) return;
        width = 640; height = size[1] * width / size[0];
      }
      const alternative = artwork.wide[name];
      if (width / height >= 2.8 && alternative) {
        const target = bridge('materializedPath', '(Ljava/lang/String;)Ljava/lang/String;',
          ['/en/sd/static_banner/gacha/sub/' + alternative]);
        if (target) {
          this.path = Memory.alloc(24);
          makeString(this.path, Memory.allocUtf8String(target));
          args[0] = this.path;
          name = alternative; size = artwork.images[name];
        }
      }
      const fitted = fitSummonArt(size[0], size[1], width, height);
      if (!fitted) return;
      this.size = Memory.alloc(8);
      this.size.writeFloat(fitted.width); this.size.add(4).writeFloat(fitted.height);
      args[1] = this.size;
      if (currentObject) offsets.set(currentObject.toString(), {dx: width - fitted.width, dy: height - fitted.height});
      if (reports++ < 16) note('SUMMON_ART_FIT file=' + name + ' source=' + size.join('x') +
        ' display=' + fitted.width.toFixed(1) + 'x' + fitted.height.toFixed(1));
    },
    onLeave() { if (this.path) freeString(this.path); }
  }));
}
