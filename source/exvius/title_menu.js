// New Game / Continue on the original title. The Info and Restore buttons are
// relabelled through the title's own text lookup. A press on either one
// starts the game through the original Tap to Start path. The online-only
// Delete Account, Support and Login Options buttons are not created: their
// builders take their own early exits. No native calls.
export function installTitleMenu(module, note, retained, bridge) {
  const str = 'NSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE';
  const exports = {
    setBtn: '_ZN10TitleScene16setBtnWithLocKeyEPN7cocos2d15SpriteBatchNodeEiiRK' +
      'NSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEESB_SB_SB_',
    getText: '_ZN9GameScene7getTextERK' + str,
    touchEnded: '_ZN10TitleScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE',
    isTouchButton: '_ZN9GameScene13isTouchButtonEiPN7cocos2d5TouchE',
    setImageBtn: '_ZN10TitleScene6setBtnEPN7cocos2d15SpriteBatchNodeEiiNSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEES9_S9_',
  };
  const address = {};
  for (const [key, name] of Object.entries(exports)) {
    address[key] = module.findExportByName(name);
    if (!address[key]) { note('LOCAL_TITLE_DISABLED missing ' + name); return; }
  }
  // Pinned GL9 TitleScene::touchEnded tags.
  const INFO = 100, RESTORE = 101;
  const HIDDEN = new Set([106, 107, 109]);  // Login Options, Support, Delete Account
  const shortString = text => {  // libc++ inline std::string, at most 22 bytes
    const value = Memory.alloc(24);
    value.writeByteArray(new Array(24).fill(0));
    value.writeU8(text.length * 2);
    value.add(1).writeUtf8String(text);
    return value;
  };
  const labels = { BTN_INFO: shortString('New Game'), BTN_RESTORE: shortString('Continue') };
  const empty = shortString('');
  const read = value => {
    const flag = value.readU8();
    const length = (flag & 1) ? value.add(8).readU64().toNumber() : flag >>> 1;
    return length > 64 ? '' : ((flag & 1) ? value.add(16).readPointer() : value.add(1)).readUtf8String(length);
  };

  // setBtnWithLocKey(scene, batch, layer, tag, layout, frame, textKey, labelLayout)
  // returns at once for a null batch node.
  let buildingButton = 0;
  retained.push(labels, empty, Interceptor.attach(address.setBtn, {
    onEnter(args) {
      if (HIDDEN.has(args[3].toInt32())) args[1] = ptr(0);
      buildingButton++;
    },
    onLeave() { buildingButton--; }
  }));
  retained.push(Interceptor.attach(address.getText, {
    onEnter(args) { this.label = buildingButton ? labels[read(args[1])] : undefined; },
    onLeave(result) { if (this.label) result.replace(this.label); }
  }));
  // setLayout's only setBtn call is the Login Options image button. An empty
  // layout name makes its layout lookup fail, and setBtn then creates nothing.
  retained.push(Interceptor.attach(address.setImageBtn, {
    onEnter(args) { args[4] = empty; }
  }));

  // A press on either button reports "not hit", so the original handler falls
  // through to its full-screen Tap to Start and loads the current save.
  let titleTouch = 0;
  retained.push(Interceptor.attach(address.touchEnded, {
    onEnter() { titleTouch++; },
    onLeave() { titleTouch--; }
  }));
  retained.push(Interceptor.attach(address.isTouchButton, {
    onEnter(args) { this.tag = titleTouch ? args[1].toInt32() : 0; },
    onLeave(result) {
      if (HIDDEN.has(this.tag)) { result.replace(ptr(0)); return; }
      if ((this.tag !== INFO && this.tag !== RESTORE) || !(result.toInt32() & 1)) return;
      if (this.tag === RESTORE) {
        note('LOCAL_TITLE_CONTINUE');
      } else {
        try {
          bridge('titleAction', '(Ljava/lang/String;)Ljava/lang/String;', ['new']);
          note('LOCAL_TITLE_NEW_GAME');
        } catch (error) {
          // The save is unchanged. Keep the original Info press rather than start it.
          note('LOCAL_TITLE_NEW_GAME_ERROR ' + error);
          return;
        }
      }
      result.replace(ptr(0));
    }
  }));
  // GL9's Options entry loads the one-page account-binding tutorial under
  // PictureStory key "option". A missing record is already a supported path.
  const optionsInit = module.findExportByName('_ZN16MenuSettingScene10initializeEv');
  const pictureStory = module.findExportByName('_ZN19PictureStoryMstList14getDispMstDataERK' + str);
  if (optionsInit && pictureStory) {
    let buildingOptions = 0;
    retained.push(Interceptor.attach(optionsInit, {
      onEnter() { buildingOptions++; },
      onLeave() { buildingOptions--; }
    }));
    retained.push(Interceptor.attach(pictureStory, {
      onEnter(args) { this.accountTutorial = buildingOptions > 0 && read(args[1]) === 'option'; },
      onLeave(result) {
        if (this.accountTutorial) {
          result.replace(ptr(0));
          note('LOCAL_OPTIONS_ACCOUNT_TUTORIAL_SUPPRESSED');
        }
      }
    }));
  }
  note('LOCAL_TITLE_READY');
}
