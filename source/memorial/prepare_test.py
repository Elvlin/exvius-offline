"""Prepare a separate 10x test copy of the existing Memorial release.

The supplied game, DEX and runtime hooks remain the baseline. Only package-local
paths, the visible test label and the verified scheduler test hook are changed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
ORIGINAL_PACKAGE = 'com.square_enix.ffbejpn'
TEST_PACKAGE = 'com.exvius.memorial.test'
APK_SHA256 = '9d21fc8b61c9900eaacb1c2ddef2cabcad1e97d2dc720be16ac09b06fc0086b4'
ANDROID = '{http://schemas.android.com/apk/res/android}'
ET.register_namespace('android', ANDROID[1:-1])

TEST_HOOK = r'''
// TEST ONLY: the unmodified release retains its original 1x speed.
(function () {
    const log = new NativeFunction(Module.getGlobalExportByName('__android_log_write'),
        'int', ['int', 'pointer', 'pointer']);
    const tag = Memory.allocUtf8String('ExviusTest');
    function note(value) { log(4, tag, Memory.allocUtf8String(value)); }
    let installed = false, attempts = 0;
    function install() {
        if (installed) return true;
        const game = Process.findModuleByName('libgame.so');
        if (!game) return false;
        const constructor = game.getExportByName('_ZN7cocos2d9SchedulerC2Ev');
        if (constructor.add(0x1c).readU32() !== 0x52a7f008 ||
            constructor.add(0x20).readU32() !== 0xb9002668) {
            throw Error('Memorial scheduler layout does not match the pinned release.');
        }
        let frames = 0, firstTime = 0;
        Interceptor.attach(game.getExportByName('_ZN7cocos2d9Scheduler6updateEf'), {
            onEnter(args) {
                const scale = args[0].add(0x24);
                scale.writeFloat(10);
                if (scale.readFloat() !== 10) throw Error('10x test speed verification failed.');
                frames++;
                if (frames === 1) {
                    firstTime = Date.now();
                    note('TEST_SPEED_VERIFIED game=Memorial scale=10 frames=1');
                } else if (frames === 300) {
                    note('TEST_SPEED_VERIFIED game=Memorial scale=10 frames=300 wall_ms=' + (Date.now() - firstTime));
                }
            }
        });
        installed = true;
        note('TEST_HOOK_READY game=Memorial speed=10');
        return true;
    }
    if (!install()) {
        const timer = setInterval(function () {
            if (install() || ++attempts >= 120) clearInterval(timer);
        }, 100);
    }
})();
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-engine', action='store_true',
                        help='Merge the built embedded gameplay component into the existing client.')
    args = parser.parse_args()
    original = PROJECT / 'repository snapshots/FFBE-Memorial-EN-Global-Events-v208.apk'
    if hashlib.sha256(original.read_bytes()).hexdigest() != APK_SHA256:
        raise ValueError('Expected the pinned existing Memorial release.')
    client = PROJECT / 'source/build/android/memorial-client'
    if not (client / 'apktool.yml').is_file():
        raise FileNotFoundError('Decode the existing Memorial APK with apktool --no-src first.')

    with zipfile.ZipFile(original) as archive:
        script = archive.read('assets/frida_script.js').decode('utf-8')
        for prefix in ('/data/data/', '/data/user/0/'):
            script = script.replace(prefix + ORIGINAL_PACKAGE + '/', prefix + TEST_PACKAGE + '/')
        if args.local_engine:
            runtime_outputs = PROJECT / 'source/build/android/local-runtime/outputs/apk/debug'
            runtime_apks = list(runtime_outputs.glob('*.apk'))
            if len(runtime_apks) != 1:
                raise FileNotFoundError('Build the single embedded runtime APK before preparing the client.')
            with zipfile.ZipFile(runtime_apks[0]) as runtime:
                original_dex = [name for name in archive.namelist()
                                if name.endswith('.dex') and '/' not in name]
                next_dex = max(1 if name == 'classes.dex' else int(name[7:-4])
                               for name in original_dex) + 1
                for name in sorted(runtime.namelist()):
                    if name.endswith('.dex') and '/' not in name:
                        target = client / ('classes' + str(next_dex) + '.dex')
                        target.write_bytes(runtime.read(name))
                        next_dex += 1
                    elif name.startswith(('assets/', 'lib/')) and not name.endswith('/'):
                        target = client / name
                        content = runtime.read(name)
                        if name in archive.namelist() and archive.read(name) != content:
                            raise FileExistsError('Runtime merge needs review for conflicting file: ' + name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
            build = PROJECT / 'source/build/android'
            (build / 'memorial-upstream.js').write_text(script, encoding='utf-8')
            (build / 'memorial-speed.js').write_text(TEST_HOOK, encoding='utf-8')
            entry = build / 'memorial-local-entry.js'
            entry.write_text("import './memorial-upstream.js';\n"
                             "import '../../memorial/local_connection.js';\n"
                             "import './memorial-speed.js';\n", encoding='utf-8')
            bundle = build / 'memorial-local.bundle.js'
            subprocess.run(['node', str(PROJECT / 'tools/vendor/android-agent/node_modules/frida-compile/dist/cli.js'),
                            str(entry), '-o', str(bundle), '-S', '-c', '-T', 'none'], check=True, cwd=PROJECT)
            shutil.copyfile(bundle, client / 'assets/frida_script.js')
        else:
            (client / 'assets/frida_script.js').write_text(script + TEST_HOOK, encoding='utf-8')
        config_path = 'lib/arm64-v8a/libfrida-gadget.config.so'
        config = json.loads(archive.read(config_path))
        config['interaction']['path'] = '/data/user/0/' + TEST_PACKAGE + '/files/frida_script.js'
        (client / config_path).write_text(json.dumps(config, indent=2), encoding='utf-8')

    manifest = client / 'AndroidManifest.xml'
    tree = ET.parse(manifest)
    root = tree.getroot()
    root.set('package', TEST_PACKAGE)
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == ANDROID + 'authorities' or element.tag in {'permission', 'uses-permission'}:
                element.set(key, value.replace(ORIGINAL_PACKAGE + '.', TEST_PACKAGE + '.'))
            if key == ANDROID + 'name' and value.startswith('.'):
                element.set(key, ORIGINAL_PACKAGE + value)
    app = root.find('application')
    label = 'Exvius Memorial TEST ONLY 10x'
    app.set(ANDROID + 'label', label)
    app.set(ANDROID + 'debuggable', 'true')
    if args.local_engine:
        for provider in list(app.findall('provider')):
            if provider.get(ANDROID + 'name') == 'com.exvius.local.LocalGameProvider':
                app.remove(provider)
        ET.SubElement(app, 'provider', {
            ANDROID + 'name': 'com.exvius.local.LocalGameProvider',
            ANDROID + 'authorities': TEST_PACKAGE + '.localgame',
            ANDROID + 'exported': 'false',
            ANDROID + 'initOrder': '2147483647',
        })
    for activity in app.findall('activity'):
        if activity.get(ANDROID + 'name') == ORIGINAL_PACKAGE + '.Lapis':
            activity.set(ANDROID + 'label', label)
    tree.write(manifest, encoding='utf-8', xml_declaration=True)
    config = client / 'apktool.yml'
    text = config.read_text(encoding='utf-8')
    text = text.replace('versionName: 11.1.1\n', 'versionName: 11.1.1-exvius-test10\n')
    if args.local_engine:
        text = text.replace('minSdkVersion: 21\n', 'minSdkVersion: 24\n')
    config.write_text(text, encoding='utf-8')
    # Apktool decodes the release's two launcher icons into both locations.
    # Keep the resource copies and omit only identical generated duplicates.
    unknown_resources = client / 'unknown/res'
    if unknown_resources.exists():
        for duplicate in unknown_resources.rglob('*'):
            if not duplicate.is_file():
                continue
            resource = client / 'res' / duplicate.relative_to(unknown_resources)
            if resource.is_file() and resource.read_bytes() == duplicate.read_bytes():
                duplicate.unlink()
    print('Prepared separate Memorial TEST ONLY 10x package using the supplied runtime.')


if __name__ == '__main__':
    main()
