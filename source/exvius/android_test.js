'use strict';
import { createNativeBridge } from './native_bridge.js';
// android_offline.py routes the game's Java callers to LocalGameBridge in the
// APK itself. Do not install the redundant URL.openConnection Java hooks:
// replacement ArtMethods in frida-java-bridge 7.0.13 crash Android 16 GC walks.
import { installSummonMenu } from './summon_menu.js';
import { installSummonArt } from './summon_art.js';
import { installAdaptiveDisplay } from './android_display.js';
import { installTitleMenu } from './title_menu.js';
import { installRaidMenu } from './raid_menu.js';
import { installMenuAssets } from './menu_assets.js';
import { installFriendsMenu } from './friends_menu.js';
import { installMapInteractionAudit } from './map_interaction_audit.js';
import { installHomeCarousel } from './home_carousel.js';

// Loaded only by the separately labelled Android test APK.
let logger;
const retained = [];

function note(message) {
  if (logger) logger(4, Memory.allocUtf8String('ExviusTest'), Memory.allocUtf8String(message));
  else console.log(message);
}

rpc.exports = {
  init(stage, parameters) {
    // 1 = the normal build (original game timing); 10 only in builds labelled TEST.
    const scale = parameters.testSpeed;
    if (scale !== 10 && scale !== 1) throw new Error('The APK requires an explicit 1x or 10x speed.');
    logger = new NativeFunction(Module.getGlobalExportByName('__android_log_write'), 'int', ['int', 'pointer', 'pointer']);
    const networkAudit = { sockets: 0, dns: 0 };
    const socketAddress = Module.getGlobalExportByName('socket');
    retained.push(Interceptor.attach(socketAddress, {
      onEnter(args) {
        const family = args[0].toInt32();
        if (family !== 2 && family !== 10) return;
        // The game library has no network use offline. Its startup interface
        // probe (AF_INET6 UDP, never connected) fails as it already does
        // without the INTERNET permission, but without reaching the network stack.
        const game = Process.findModuleByName('libgame.so');
        if (game && this.returnAddress.compare(game.base) >= 0 &&
            this.returnAddress.compare(game.base.add(game.size)) < 0) {
          args[0] = ptr(-1);
          note('OFFLINE_NETWORK_SOCKET_BLOCKED caller=' + DebugSymbol.fromAddress(this.returnAddress));
          return;
        }
        networkAudit.sockets += 1;
        if (networkAudit.sockets <= 16)
          note('OFFLINE_NETWORK_SOCKET_ATTEMPT caller=' + DebugSymbol.fromAddress(this.returnAddress));
      }
    }));
    for (const symbol of ['getaddrinfo', 'gethostbyname']) {
      const address = Module.findGlobalExportByName(symbol);
      if (!address) continue;
      retained.push(Interceptor.attach(address, {
        onEnter(args) {
          if (args[0].isNull()) return;
          const host = args[0].readUtf8String();
          if (host === 'localhost' || host === '::1' || host.startsWith('127.')) return;
          networkAudit.dns += 1;
          if (networkAudit.dns <= 16)
            note('OFFLINE_NETWORK_DNS_ATTEMPT host=' + host + ' caller=' + DebugSymbol.fromAddress(this.returnAddress));
        }
      }));
    }
    note('OFFLINE_IO_AUDIT_READY');
    let installed = false;
    function installGameHook() {
        if (installed) return;
        const module = Process.findModuleByName('libgame.so');
        if (!module) return;
        // The native startup also initializes Firebase directly, independently
        // of the disabled Java bridge. Offline builds have no messaging service.
        const skipFirebase = new NativeCallback(function () { return 0; }, 'bool', ['pointer', 'pointer']);
        retained.push(skipFirebase);
        Interceptor.replaceFast(module.getExportByName(
          '_ZN12FirebaseWrap10initializeERKNSt6__ndk16vectorI15FirebaseModulesNS0_9allocatorIS2_EEEE'), skipFirebase);
        // Missing archive images otherwise enter the retired Java reporting
        // service from inside the native texture reader. Keep offline failures
        // local instead of invoking that service during scene construction.
        const skipReport = new NativeCallback(function () {}, 'void', ['pointer', 'pointer', 'bool']);
        retained.push(skipReport);
        Interceptor.replaceFast(module.getExportByName(
          '_ZN7Reports3logERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_b'), skipReport);
        note('OFFLINE_NATIVE_REPORTING_DISABLED');
        let installing = 'summon menu';
        try {
        const bridge = createNativeBridge(module);
        // Android 16's Region parcel reader can pass a null AParcel during
        // screenshot/accessibility requests. Its array reader dereferences
        // that pointer before returning a status (the device crash is at
        // ReadArray+0x34). Reject only that invalid input in this process.
        // Valid parcels keep Android's original implementation and ABI.
        const binder = Process.findModuleByName('libbinder_ndk.so');
        const readArrayAddress = binder?.findExportByName('AParcel_readInt32Array');
        if (readArrayAddress) {
          let readArray;
          let rejectedParcel = false;
          const guardedArray = new NativeCallback(function (parcel, array, allocator) {
            if (parcel.isNull()) {
              if (!rejectedParcel) { note('ANDROID_INVALID_REGION_PARCEL_REJECTED'); rejectedParcel = true; }
              return -22; // STATUS_BAD_VALUE
            }
            return readArray(parcel, array, allocator);
          }, 'int', ['pointer', 'pointer', 'pointer']);
          readArray = new NativeFunction(Interceptor.replaceFast(readArrayAddress, guardedArray),
            'int', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
          retained.push(guardedArray);
          note('ANDROID_REGION_PARCEL_GUARD_READY');
        }
        if (parameters.mapInteractionAudit) installMapInteractionAudit(module, note, retained);
        installing = 'Home carousel';
        const homeCarousel = installHomeCarousel(module, note, retained);
        installing = 'summon menu';
        const modeChooserName = installSummonMenu(module, note, retained, bridge, homeCarousel);
        installing = 'summon art';
        installSummonArt(module, note, retained, bridge);
        installing = 'title';
        installTitleMenu(module, note, retained, bridge);
        installing = 'raid';
        installRaidMenu(module, note, retained, bridge);
        installing = 'menu assets';
        installMenuAssets(module, note, retained, bridge, modeChooserName);
        installing = 'friends';
        installFriendsMenu(module, note, retained);
        const update = module.getExportByName('_ZN7cocos2d9Scheduler6updateEf');
        const constructor = module.getExportByName('_ZN7cocos2d9SchedulerC2Ev');
        if (constructor.add(0x1c).readU32() !== 0x52a7f008 ||
            constructor.add(0x20).readU32() !== 0xb9002668) {
          throw new Error('The pinned Global scheduler layout changed.');
        }
        installing = 'display';
        installAdaptiveDisplay(module, retained, note, bridge);
        function text(p) {
          const flag = p.readU8();
          const length = (flag & 1) ? p.add(8).readU64().toNumber() : flag >>> 1;
          if (length > 4096) return '<invalid>';
          return ((flag & 1) ? p.add(16).readPointer() : p.add(1)).readUtf8String(length);
        }
        // All three original CRI queue overloads call this implementation.
        // Existing local files are ready for the game's normal parser/binder.
        // A missing file stays a native file error, without invoking CRI HTTP.
        const openFile = new NativeFunction(Module.getGlobalExportByName('open'), 'int', ['pointer', 'int']);
        const readFile = new NativeFunction(Module.getGlobalExportByName('read'), 'long', ['int', 'pointer', 'ulong']);
        const closeFile = new NativeFunction(Module.getGlobalExportByName('close'), 'int', ['int']);
        const probe = Memory.alloc(1);
        // Use the original filesystem-capable installer, rather than the
        // separate WebInstaller which initializes an HTTP engine on creation.
        retained.push(Interceptor.attach(module.getExportByName('_ZN20sgWrapCriFsInstaller18useLegacyInstallerEv'), {
          onLeave(result) { result.replace(1); }
        }));
        // Recovery now restarts the original local loading flow. Retain the
        // installed files instead of deleting them for an online redownload.
        Interceptor.replaceFast(
          module.getExportByName('_ZN17TitleRecoverScene20setDeleteCacheLayoutEv'),
          module.getExportByName('_ZN17TitleRecoverScene21changeInitializeSceneEv'));
        Interceptor.replaceFast(
          module.getExportByName('_ZN28TitleResourceErrorGuideScene20setDeleteCacheLayoutEv'),
          module.getExportByName('_ZN28TitleResourceErrorGuideScene15changeNextSceneEv'));
        const addFileAddress = module.getExportByName('_ZN16CriFileInstaller11addLoadFileERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_S8_iii');
        let addLocalFile;
        let nativeFileHits = 0;
        const addFile = new NativeCallback(function (installer, destination, source, key, size, priority, group) {
          const address = text(source);
          if (!/^https?:\/\//i.test(address))
            return addLocalFile(installer, destination, source, key, size, priority, group);
          const path = text(destination);
          const descriptor = openFile(Memory.allocUtf8String(path), 0);
          if (descriptor >= 0) {
            let ready;
            try { ready = Number(readFile(descriptor, probe, 1)) === 1; }
            finally { closeFile(descriptor); }
            if (ready) {
              nativeFileHits += 1;
              if (nativeFileHits <= 8) note('LOCAL_NATIVE_FILE_READY path=' + path);
              return;
            }
          }
          let supplied = false;
          try {
            supplied = bridge('materializeFile', '(Ljava/lang/String;Ljava/lang/String;)Z', [address, path], 'bool');
          } catch (error) { note('LOCAL_NATIVE_FILE_SUPPLY_ERROR ' + error); }
          if (supplied) {
            note('LOCAL_NATIVE_FILE_SUPPLIED path=' + path);
            return;
          }
          note('LOCAL_NATIVE_FILE_MISSING path=' + path);
          addLocalFile(installer, destination, destination, key, size, priority, group);
        }, 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'int', 'int', 'int']);
        retained.push(addFile, probe);
        addLocalFile = new NativeFunction(Interceptor.replaceFast(addFileAddress, addFile),
          'void', ['pointer', 'pointer', 'pointer', 'pointer', 'int', 'int', 'int'], {exceptions: 'propagate'});
        let fileRequests = 0;
        // Reuse the native loading indicator and its actual request lifecycle.
        // TextManager returns a const string reference, so retain these labels.
        const loadingLabels = {};
        for (const [key, value] of Object.entries({CONNECT: 'Loading...', CONNECTING: 'Loading'})) {
          const label = Memory.alloc(24);
          label.writeByteArray(new Uint8Array(24));
          label.writeU8(value.length * 2);
          label.add(1).writeUtf8String(value);
          loadingLabels[key] = label;
          retained.push(label);
        }
        const loggedLabels = new Set();
        retained.push(Interceptor.attach(module.getExportByName('_ZN11TextManager7getTextERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE'), {
          onEnter(args) { this.key = text(args[1]); },
          onLeave(result) {
            const replacement = loadingLabels[this.key];
            if (!replacement) return;
            result.replace(replacement);
            if (!loggedLabels.has(this.key)) {
              loggedLabels.add(this.key);
              note('LOCAL_LOADING_LABEL key=' + this.key);
            }
          }
        }));
        // Local assets already exist. Disable the optional DLC prompt, while
        // retaining the original file checks and in-process resource reads.
        retained.push(Interceptor.attach(module.getExportByName('_ZNK14UserConfigInfo26isDlcDownloadPromptEnabledEv'), {
          onLeave(result) { result.replace(0); }
        }));
        retained.push(Interceptor.attach(module.getExportByName('_ZN14UserConfigInfo27setDlcDownloadPromptEnabledEb'), {
          onEnter(args) { args[1] = ptr(0); }
        }));
        // The tutorial notice checks this preference, independently of the
        // optional DLC setting and the tutorial's saved switch. Local assets
        // are already installed, so use the native 'choice already made' path.
        retained.push(Interceptor.attach(module.getExportByName('_ZNK20BackgroundDownloader33getUserSelectedDownloadPreferenceEv'), {
          onLeave(result) { result.replace(1); }
        }));
        // First run: the title asks which online account to bind when no login
        // service is active. TitleScene::updateEvent then calls startGame
        // instead, whose hook below selects the local guest. Only this pinned
        // call site sees the change; other screens keep the real login state.
        const titleLoginCheck = module.base.add(0x1e5ad78);
        if (titleLoginCheck.readU32() === 0x97d45886 && titleLoginCheck.add(4).readU32() === 0x36000080) {
          const titleLoginReturn = titleLoginCheck.add(4);
          retained.push(Interceptor.attach(module.getExportByName('_ZNK19LoginServiceManager10isLoggedInEv'), {
            onEnter() { this.title = this.returnAddress.equals(titleLoginReturn); },
            onLeave(result) { if (this.title) result.replace(1); }
          }));
        } else {
          note('LOCAL_ACCOUNT_PROMPT_UNCHANGED unexpected title layout');
        }
        // Offline builds have no ad SDKs. Report the age/consent question as
        // answered so it is never shown; ads stay non-personalised (disabled).
        retained.push(Interceptor.attach(module.getExportByName('_ZNK14UserConfigInfo24isPersonalizedAdsCheckedEv'), {
          onLeave(result) { result.replace(1); }
        }));
        // The banner downloader (FileDownloadManager) queues a request per image and only
        // draws the image once that request finishes; offline its queue never starts, so the
        // list showed the file name. Supply each file from the local engine as it is queued,
        // and report no pending request for a file that is already on disk.
        const fileReady = path => {
          const descriptor = openFile(Memory.allocUtf8String(path), 0);
          if (descriptor < 0) return false;
          try { return Number(readFile(descriptor, probe, 1)) === 1; }
          finally { closeFile(descriptor); }
        };
        for (const name of [
          '_ZN19FileDownloadManager13createRequestERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_m'
        ]) retained.push(Interceptor.attach(module.getExportByName(name), {
          onEnter(args) {
            fileRequests += 1;
            const address = text(args[1]), path = text(args[2]);
            if (fileRequests <= 24)
              note('LOCAL_FILE_REQUEST url=' + address + ' destination=' + path);
            else if ((fileRequests & (fileRequests - 1)) === 0)
              note('LOCAL_FILE_REQUEST_COUNT total=' + fileRequests);
            if (!/^https?:\/\//i.test(address) || fileReady(path)) return;
            let supplied = false;
            try {
              supplied = bridge('materializeFile', '(Ljava/lang/String;Ljava/lang/String;)Z', [address, path], 'bool');
            } catch (error) { note('LOCAL_DOWNLOAD_SUPPLY_ERROR ' + error); }
            note((supplied ? 'LOCAL_DOWNLOAD_SUPPLIED path=' : 'LOCAL_DOWNLOAD_MISSING path=') + path);
          }
        }));
        retained.push(Interceptor.attach(module.getExportByName(
          '_ZNK19FileDownloadManager10hasRequestERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_'), {
          onEnter(args) { this.paths = [text(args[1]), text(args[2])]; },
          onLeave(result) {
            if (!result.isNull() && this.paths.some(path => path.startsWith('/') && fileReady(path))) result.replace(0);
          }
        }));
        retained.push(Interceptor.attach(module.getExportByName('_ZN19DownloadMstFileList3addERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEiiiS8_b'), {
          onEnter(args) { note('LOCAL_TABLE_CHECK name=' + text(args[1]) + ' version=' + args[2].toInt32() + ' old=' + args[3].toInt32() + ' bytes=' + args[4].toInt32()); }
        }));
        const selectGuest = new NativeFunction(module.getExportByName('_ZN19LoginServiceManager18selectLoginServiceEi'), 'void', ['pointer', 'int'], {exceptions: 'propagate'});
        const forceGuest = new NativeFunction(module.getExportByName('_ZN19LoginServiceManager22setIsForceLoginAsGuestEb'), 'void', ['pointer', 'bool'], {exceptions: 'propagate'});
        retained.push(Interceptor.attach(module.getExportByName('_ZN10TitleScene9startGameEv'), {
          onEnter() {
            const login = module.getExportByName('_ZZN19LoginServiceManager6sharedEvE9singleton').readPointer();
            if (!login.isNull()) {
              selectGuest(login, 0);
              forceGuest(login, 1);
              note('LOCAL_GUEST original title start');
            }
          }
        }));
        let frames = 0;
        let firstTime = 0;
        retained.push(Interceptor.attach(update, {
          onEnter(args) {
            // GL9 arm64 constructor and update disassembly both identify this float.
            if (scale !== 1) {
              const timeScale = args[0].add(0x24);
              timeScale.writeFloat(scale);
              if (timeScale.readFloat() !== scale) throw new Error('Game-time speed verification failed.');
            }
            frames += 1;
            if (frames === 1) {
              firstTime = Date.now();
              note('SPEED_VERIFIED scale=' + scale + ' frames=1');
            } else if (frames === 300) {
              note('SPEED_VERIFIED scale=' + scale + ' frames=300 wall_ms=' + (Date.now() - firstTime));
            }
            if (frames % 3600 === 0)
              note('OFFLINE_IO_AUDIT sockets=' + networkAudit.sockets + ' dns=' + networkAudit.dns + ' files=' + fileRequests);
          }
        }));
        installed = true;
        note('TEST_HOOK_READY game=GL9 original-ui architecture=' + Process.arch);
        } catch (error) {
          installed = true;
          note('STARTUP_HOOK_FAILED component=' + installing + ' error=' + error + ' stack=' + error.stack);
        }
    }
    // Use public loader entry points after the module-observer startup path
    // triggered a native linker abort on this Android 16 test device.
    const missingLibrary = Memory.allocUtf8String('/nonexistent/libaudioclientimpl.so');
    retained.push(missingLibrary);
    ['android_dlopen_ext', 'dlopen'].forEach(symbol => {
      const address = Module.findGlobalExportByName(symbol);
      if (!address) return;
      retained.push(Interceptor.attach(address, {
        onEnter(args) {
          const path = args[0].isNull() ? '' : args[0].readUtf8String();
          this.isGame = path.endsWith('libgame.so');
          // This phone's AudioTrack::releaseBuffer calls AudioClientStub::dumpAudioDataToFile, which
          // dlopens libaudioclientimpl.so for every audio buffer. The lookup fails, and each failure
          // re-scans this 800 MB APK's zip directory: the AudioTrack thread ran at 100% CPU and the track
          // underran (heard as crackling). Ask for an absolute path that does not exist instead: one failed
          // open, the same NULL handle the stub always got (a non-null handle crashes it), no archive scan.
          if (path === 'libaudioclientimpl.so') args[0] = missingLibrary;
        },
        onLeave(result) {
          if (this.isGame && !result.isNull()) installGameHook();
        }
      }));
    });
    installGameHook();
    note('initialized stage=' + stage + ' speed=' + scale);
  }
};
