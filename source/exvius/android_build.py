"""Prepare the explicitly labelled GL9 Android test APK without device-wide changes.

Uses Frida Gadget's non-rooted-device workflow. Originals remain in the
repository snapshots folder. This command prepares files; apktool and apksigner
perform the build and signing afterwards.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import subprocess
import zipfile
import xml.etree.ElementTree as ET
import argparse
import os

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'tools/vendor/python'))
sys.path.insert(0, str(PROJECT / 'source/server'))
from android_offline import prepare_offline_code

ANDROID = '{http://schemas.android.com/apk/res/android}'
ET.register_namespace('android', ANDROID[1:-1])
APK_HASH = '955deacfbe4b3d0cd04e2947eb005e310915ba98132d71216626bfb3554ad246'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-engine', action='store_true',
                        help='Merge the built embedded engine into the original Global client.')
    parser.add_argument('--speed', type=int, choices=(1, 10), default=10,
                        help='Game speed: 1 for the normal build, 10 only for the build labelled TEST.')
    parser.add_argument('--map-interaction-audit', action='store_true',
                        help='Read-only native map touch tracing in an explicitly labelled test build.')
    parser.add_argument('--release-version', help='Android display version for a distribution build.')
    parser.add_argument('--release-code', type=int, help='Increasing Android version code for replacement updates.')
    args = parser.parse_args()
    label = 'Exvius TEST ONLY 10x' if args.speed == 10 else 'Exvius'
    if args.map_interaction_audit:
        label = 'Exvius TEST MAP ' + str(args.speed) + 'x'
    if not args.local_engine:
        parser.error('The original UI build now requires --local-engine for local gameplay.')
    original = PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk'
    if hashlib.sha256(original.read_bytes()).hexdigest() != APK_HASH:
        raise ValueError('Expected the verified original Global v9.0.0 APK.')
    client = PROJECT / 'source/build/android/client'
    if not (client / 'apktool.yml').is_file():
        raise ValueError('Decode the original APK with apktool --no-src first.')
    prepare_offline_code(client)
    # Compile only the startup provider. The discarded replacement menu must
    # not remain in the installed test DEX through an older generated artifact.
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or
               (Path.home() / 'AppData/Local/Android/Sdk'))
    android_jar = sdk / 'platforms/android-33/android.jar'
    startup_classes = PROJECT / 'source/build/android/init-classes'
    startup_dex = PROJECT / 'source/build/android/init-dex'
    startup_classes.mkdir(exist_ok=True)
    startup_dex.mkdir(exist_ok=True)
    subprocess.run(['javac', '-source', '8', '-target', '8', '-bootclasspath', str(android_jar),
                    '-d', str(startup_classes), str(PROJECT / 'source/exvius/android/TestInitProvider.java')], check=True)
    subprocess.run([str(sdk / 'build-tools/36.0.0/d8.bat'), '--lib', str(android_jar),
                    '--min-api', '24', '--output', str(startup_dex),
                    str(startup_classes / 'com/exvius/offline/test/TestInitProvider.class')], check=True)
    shutil.copyfile(startup_dex / 'classes.dex', client / 'classes4.dex')
    runtime_outputs = PROJECT / 'source/build/android/local-runtime/outputs/apk/debug'
    runtime_apks = list(runtime_outputs.glob('*.apk'))
    if len(runtime_apks) != 1:
        raise FileNotFoundError('Build the existing embedded runtime component first.')
    with zipfile.ZipFile(original) as baseline, zipfile.ZipFile(runtime_apks[0]) as runtime:
        # DEX 4 is the existing startup provider. DEX 5 adds the local engine.
        next_dex = 5
        original_members = set(baseline.namelist())
        for name in sorted(runtime.namelist()):
            if name.endswith('.dex') and '/' not in name:
                (client / ('classes' + str(next_dex) + '.dex')).write_bytes(runtime.read(name))
                next_dex += 1
            elif name.startswith(('assets/', 'lib/')) and not name.endswith('/'):
                content = runtime.read(name)
                if name in original_members and baseline.read(name) != content:
                    raise FileExistsError('Local component conflicts with original member: ' + name)
                target = client / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    # Edited original assets (data/apk_overlay mirrors the APK layout): the boot loading animation's
    # baked "Connecting" lettering replaced with the same atlas's own "Loading" art (originals in
    # data/state/backups/originals).
    overlay = PROJECT / 'data/apk_overlay'
    for source in sorted(overlay.rglob('*')) if overlay.is_dir() else []:
        if source.is_file():
            target = client / source.relative_to(overlay)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            print('Applied asset overlay:', source.relative_to(overlay).as_posix(), flush=True)
    with zipfile.ZipFile(original) as archive:
        original_game = archive.read('lib/arm64-v8a/libgame.so')
    native = client / 'lib/arm64-v8a'
    (native / 'libgame.so').write_bytes(original_game)
    # Reject another client layout instead of applying a guessed memory offset.
    expected = bytes.fromhex('08f0a752682600b9')
    # The pinned original ELF maps this constructor's address directly to file offset.
    if original_game[0x2ae0fb4:0x2ae0fbc] != expected:
        raise ValueError('GL9 scheduler constructor does not match the verified layout.')
    print('Original game native library retained byte for byte.', flush=True)
    shutil.copyfile(PROJECT / 'tools/vendor/frida-gadget-17.24.3-android-arm64.so', native / 'libexviustest.so')
    bundle = PROJECT / 'source/build/android/android_test.bundle.js'
    subprocess.run(['node', str(PROJECT / 'tools/vendor/android-agent/node_modules/frida-compile/dist/cli.js'),
                    str(Path(__file__).with_name('android_test.js')), '-o', str(bundle),
                    '-S', '-c', '-T', 'none'], check=True, cwd=PROJECT)
    if b'frida-java-bridge' in bundle.read_bytes():
        raise ValueError('Global Java transport must stay in the APK. Runtime Java method replacement crashes Android 16 GC.')
    shutil.copyfile(bundle, native / 'libexviustest.js.so')
    (native / 'libexviustest.config.so').write_text(json.dumps({
        'interaction': {'type': 'script', 'path': 'libexviustest.js.so',
                        'parameters': {'testSpeed': args.speed,
                                       'mapInteractionAudit': args.map_interaction_audit}},
        'runtime': 'qjs'
    }, indent=2), encoding='utf-8')

    # This arm64 phone test package must not silently offer an uninstrumented ABI.
    arm32 = client / 'lib/armeabi-v7a'
    if arm32.exists():
        for path in arm32.iterdir():
            if path.is_file():
                path.unlink()
        arm32.rmdir()
    (client / 'res/raw/exvius_test_ca.pem').unlink(missing_ok=True)
    # Keep the resource ID used by the original DEX, without any test CA trust.
    (client / 'res/xml/network_security_config.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<network-security-config><base-config cleartextTrafficPermitted="false" />'
        '</network-security-config>\n', encoding='utf-8')
    manifest = client / 'AndroidManifest.xml'
    tree = ET.parse(manifest)
    original_package = 'com.square_enix.android_googleplay.FFBEWW'
    test_package = 'com.exvius.offline.test'
    tree.getroot().set('package', test_package)
    for permission in list(tree.getroot().findall('uses-permission')):
        if permission.get(ANDROID + 'name') in {
            'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE',
            'android.permission.ACCESS_WIFI_STATE', 'android.permission.CHANGE_WIFI_STATE',
            'android.permission.USE_CREDENTIALS', 'com.android.vending.BILLING',
            'com.google.android.gms.permission.AD_ID',
            'com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE',
            'com.google.android.c2dm.permission.RECEIVE',
            'android.permission.ACCESS_ADSERVICES_ATTRIBUTION',
            'android.permission.ACCESS_ADSERVICES_AD_ID',
        }:
            tree.getroot().remove(permission)
    # Only the standard Android updater uses online downloads. Gameplay keeps
    # the existing local connection adapter and blocked native network paths.
    for name in ('android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE',
                 'android.permission.REQUEST_INSTALL_PACKAGES'):
        if not any(p.get(ANDROID + 'name') == name for p in tree.getroot().findall('uses-permission')):
            ET.SubElement(tree.getroot(), 'uses-permission', {ANDROID + 'name': name})
    for provider in tree.getroot().iter('provider'):
        authority = provider.get(ANDROID + 'authorities')
        if authority:
            provider.set(ANDROID + 'authorities', authority.replace(original_package, test_package))
    app = tree.getroot().find('application')
    # Permit the game surface to use modern portrait displays. Cocos handles
    # proportional canvas expansion in android_display.js.
    app.set(ANDROID + 'resizeableActivity', 'true')
    app.attrib.pop(ANDROID + 'networkSecurityConfig', None)
    sdk_prefixes = ('com.google.', 'com.facebook.', 'com.appsflyer.', 'com.tapjoy.',
                    'com.ironsource.', 'com.unity3d.', 'com.android.billingclient.',
                    'backtraceio.', 'com.helpshift.', 'io.helpshift.', 'androidx.work.')
    for component in list(app):
        name = component.get(ANDROID + 'name', '')
        if component.tag in {'activity', 'provider', 'service', 'receiver'} and (
                name.startswith(sdk_prefixes) or name in {
                    original_package + '.RegistrationIntentService',
                    original_package + '.LapisFirebaseListenerService',
                }):
            app.remove(component)
        elif name == 'androidx.startup.InitializationProvider':
            for initializer in list(component):
                if initializer.get(ANDROID + 'name', '').startswith(sdk_prefixes):
                    component.remove(initializer)
    # Play Games v2 registers automatic sign-in from this startup provider.
    # Offline play uses the local server's fresh guest save instead.
    for provider in list(app.findall('provider')):
        if provider.get(ANDROID + 'name') in {
            'com.google.android.gms.games.provider.PlayGamesInitProvider',
            'com.google.android.gms.ads.MobileAdsInitProvider',
            'com.google.firebase.provider.FirebaseInitProvider',
            'com.facebook.internal.FacebookInitProvider',
            'com.facebook.ads.AudienceNetworkContentProvider',
            'com.ironsource.lifecycle.IronsourceLifecycleProvider',
        }:
            app.remove(provider)
    offline_metadata = {
        'firebase_analytics_collection_deactivated': 'true',
        'firebase_messaging_auto_init_enabled': 'false',
        'firebase_crashlytics_collection_enabled': 'false',
        'com.facebook.sdk.AutoLogAppEventsEnabled': 'false',
        'com.facebook.sdk.AdvertiserIDCollectionEnabled': 'false',
    }
    for name, value in offline_metadata.items():
        for metadata in list(app.findall('meta-data')):
            if metadata.get(ANDROID + 'name') == name:
                app.remove(metadata)
        ET.SubElement(app, 'meta-data', {ANDROID + 'name': name, ANDROID + 'value': value})
    for provider in list(app.findall('provider')):
        if provider.get(ANDROID + 'name') == 'com.exvius.offline.test.TestInitProvider':
            app.remove(provider)
    ET.SubElement(app, 'provider', {
        ANDROID + 'name': 'com.exvius.offline.test.TestInitProvider',
        ANDROID + 'authorities': test_package + '.init',
        ANDROID + 'exported': 'false',
        ANDROID + 'initOrder': '2147483647',
    })
    for provider in list(app.findall('provider')):
        if provider.get(ANDROID + 'name') == 'com.exvius.local.LocalGameProvider':
            app.remove(provider)
    ET.SubElement(app, 'provider', {
        ANDROID + 'name': 'com.exvius.local.LocalGameProvider',
        ANDROID + 'authorities': test_package + '.localgame',
        ANDROID + 'exported': 'false',
        ANDROID + 'initOrder': '2147483647',
    })
    app.set(ANDROID + 'label', label)
    for activity in app.findall('activity'):
        if activity.get(ANDROID + 'name') == original_package + '.Lapis':
            activity.set(ANDROID + 'label', label)
            activity.set(ANDROID + 'resizeableActivity', 'true')
    app.set(ANDROID + 'debuggable', 'false' if args.release_code else 'true')
    if args.release_version:
        tree.getroot().set(ANDROID + 'versionName', args.release_version)
    if args.release_code:
        tree.getroot().set(ANDROID + 'versionCode', str(args.release_code))
    for activity in list(app.findall('activity')):
        if activity.get(ANDROID + 'name') == 'com.exvius.local.DataDownloadActivity':
            app.remove(activity)
            continue
        for intent in list(activity.findall('intent-filter')):
            if any(category.get(ANDROID + 'name') == 'android.intent.category.LAUNCHER'
                   for category in intent.findall('category')):
                activity.remove(intent)
    launcher = ET.SubElement(app, 'activity', {
        ANDROID + 'name': 'com.exvius.local.DataDownloadActivity',
        ANDROID + 'exported': 'true', ANDROID + 'screenOrientation': 'portrait',
        ANDROID + 'theme': '@android:style/Theme.Material.NoActionBar',
        ANDROID + 'label': 'Exvius Offline',
    })
    intent = ET.SubElement(launcher, 'intent-filter')
    ET.SubElement(intent, 'action', {ANDROID + 'name': 'android.intent.action.MAIN'})
    ET.SubElement(intent, 'category', {ANDROID + 'name': 'android.intent.category.LAUNCHER'})
    tree.write(manifest, encoding='utf-8', xml_declaration=True)
    config = client / 'apktool.yml'
    text = config.read_text(encoding='utf-8')
    suffix = '-exvius-test10' if args.speed == 10 else '-exvius'
    import re
    text = re.sub(r'(?m)^(\s*)versionName: 9\.0\.0(?:-exvius(?:-test10)?)?$', r'\g<1>versionName: 9.0.0' + suffix, text)
    text = text.replace('minSdkVersion: 21\n', 'minSdkVersion: 24\n')
    if args.release_version:
        text = re.sub(r'(?m)^(\s*)versionName:.*$', r'\g<1>versionName: ' + args.release_version, text)
    if args.release_code:
        text = re.sub(r'(?m)^(\s*)versionCode:.*$', r'\g<1>versionCode: ' + str(args.release_code), text)
    config.write_text(text, encoding='utf-8')
    print('Prepared arm64 client "' + label + '" at ' + str(args.speed) + 'x. Normal original APK is unchanged.')


if __name__ == '__main__':
    main()
