// Retain the original Friends screens and local companion gifts.
// External invitations and account linking use native disabled buttons.
export function installFriendsMenu(module, note, retained) {
  const fn = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const enable = fn('_ZN12SpriteButton11setIsEnableEb', 'void', ['pointer', 'bool']);
  const touchEnable = fn('_ZN12SpriteButton14setTouchEnableEb', 'void', ['pointer', 'bool']);
  const base = fn('_ZN12SpriteButton13getBaseSpriteEv', 'pointer', ['pointer']);
  const caption = fn('_ZNK12SpriteButton20getBaseCaptionSpriteEv', 'pointer', ['pointer']);
  const opacity = fn('_ZN7cocos2d4Node10setOpacityEh', 'void', ['pointer', 'uchar']);
  const blocked = new Set(['share_btn', 'facebook_btn', 'reinforcement_setting_btn']);
  const topFrames = [];
  function value(text) {
    const tag = text.readU8();
    const length = tag & 1 ? text.add(8).readU64().toNumber() : tag >>> 1;
    if (length > 256) return '';
    return (tag & 1 ? text.add(16).readPointer() : text.add(1)).readUtf8String(length);
  }
  const assign = fn('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6assignEPKcm',
    'pointer', ['pointer', 'pointer', 'uint64']);
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN9GameUtils16getFriendIDCommaENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE'), {
    onEnter(args) {
      // The offline profile has no server-issued nine-digit friend code.
      // Scope this to the own-profile caption, preserving searched NPC IDs
      // and the native validation of text entered into the search field.
      if (this.returnAddress.equals(module.base.add(0x211689c)) && !/^\d{9}$/.test(value(args[0])))
        this.output = this.context.x8;
    },
    onLeave() {
      if (!this.output) return;
      const text = 'Local profile';
      assign(this.output, Memory.allocUtf8String(text), text.length);
      note('OFFLINE_FRIENDS_LOCAL_PROFILE');
    }
  }));
  function disable(button) {
    if (button.isNull()) return;
    enable(button, 0);
    touchEnable(button, 0);
    for (const sprite of [base(button), caption(button)])
      if (!sprite.isNull()) opacity(sprite, 95);
  }
  retained.push(Interceptor.attach(module.getExportByName('_ZN14FriendTopScene9setLayoutEv'), {
    onEnter() { topFrames.push([]); },
    onLeave() {
      for (const button of topFrames.pop()) disable(button);
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN14FriendTopScene6setBtnEiiNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEiS6_ifb'), {
    onEnter(args) { this.name = value(args[3]); },
    onLeave(button) {
      if (!blocked.has(this.name)) return;
      // setBtn returns its SpriteButton directly in x0. The layout helper
      // does not register it through the addSpriteButtonList overload.
      disable(button);
      // Frida recycles onLeave's return-value wrapper after this callback.
      if (topFrames.length) topFrames[topFrames.length - 1].push(ptr(button.toString()));
      note('OFFLINE_FRIENDS_DISABLED button=' + this.name);
    }
  }));
}
