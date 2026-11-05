// Runs the actual startup source with Frida API mocks. This is not a device test.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = process.argv[2] || __dirname + '/android_test.js';
const source = fs.readFileSync(path, 'utf8').replace(/^import .*;\r?\n/gm, '');

class Ptr {
  constructor(value) {
    this.value = value;
  }

  isNull() {
    return this.value === null;
  }

  readUtf8String() {
    return this.value;
  }

  toString() {
    return String(this.value);
  }
}

function start(resolution = 'linker') {
  const hooks = new Map();
  const logs = [];
  let gameLookups = 0;
  const valid = new Set(['__loader_dlopen', '__loader_android_dlopen_ext']);
  const linker = {
    findExportByName: name => resolution === 'linker' && valid.has(name) ? new Ptr(name) : null,
  };
  const context = {
    console,
    rpc: {exports: {}},
    Memory: {allocUtf8String: value => new Ptr(value)},
    Module: {
      getGlobalExportByName: name => new Ptr(name),
      findGlobalExportByName: name => resolution !== 'missing' || !name.startsWith('__loader_')
        ? new Ptr(name)
        : null,
    },
    Process: {
      findModuleByName(name) {
        if (name === 'libgame.so') {
          gameLookups++;
          return null;
        }
        if (name === 'linker64') return linker;
        return null;
      },
    },
    NativeFunction: function () {
      return (_priority, _tag, message) => logs.push(String(message));
    },
    Interceptor: {
      attach(address, handler) {
        hooks.set(String(address), handler);
        return {};
      },
    },
  };
  vm.runInNewContext(source, context, {filename: path});
  context.rpc.exports.init('early', {testSpeed: 1});
  return {hooks, logs, lookups: () => gameLookups};
}

const tests = [];
function test(name, callback) {
  callback();
  tests.push(name);
}

const run = start();
test('Registers both inner loader exports, never public wrappers', () => {
  assert(run.hooks.has('__loader_dlopen'));
  assert(run.hooks.has('__loader_android_dlopen_ext'));
  assert(!run.hooks.has('dlopen'));
  assert(!run.hooks.has('android_dlopen_ext'));
});

for (const symbol of ['__loader_dlopen', '__loader_android_dlopen_ext']) {
  test(symbol + ' preserves vendor path, flags, extinfo and real caller', () => {
    for (const vendor of ['/vendor/lib64/hw/mapper.mediatek.so', '/vendor/lib64/hw/gralloc.qcom.so']) {
      const args = [
        new Ptr(vendor),
        new Ptr('RTLD_NOW'),
        new Ptr('extinfo-or-caller'),
        new Ptr('real-caller'),
      ];
      const before = [...args];
      const call = {};
      const count = run.lookups();
      run.hooks.get(symbol).onEnter.call(call, args);
      args.forEach((arg, index) => assert.strictEqual(arg, before[index]));
      run.hooks.get(symbol).onLeave.call(call, new Ptr('loaded-handle'));
      assert.equal(run.lookups(), count);
    }
  });

  test(symbol + ' triggers game installation only after successful libgame load', () => {
    const hook = run.hooks.get(symbol);
    const call = {};
    const count = run.lookups();
    hook.onEnter.call(call, [new Ptr('/app/libgame.so')]);
    assert.equal(run.lookups(), count);
    hook.onLeave.call(call, new Ptr(null));
    assert.equal(run.lookups(), count);
    hook.onLeave.call(call, new Ptr('game-handle'));
    assert.equal(run.lookups(), count + 1);
  });

  test(symbol + ' keeps narrow audio workaround without changing caller', () => {
    const args = [
      new Ptr('libaudioclientimpl.so'),
      new Ptr('flags'),
      new Ptr('ext-or-caller'),
      new Ptr('caller'),
    ];
    const before = [...args];
    run.hooks.get(symbol).onEnter.call({}, args);
    assert.equal(args[0].value, '/nonexistent/libaudioclientimpl.so');
    for (let index = 1; index < args.length; index++) assert.strictEqual(args[index], before[index]);
    const absolute = [new Ptr('/vendor/lib64/libaudioclientimpl.so')];
    run.hooks.get(symbol).onEnter.call({}, absolute);
    assert.equal(absolute[0].value, '/vendor/lib64/libaudioclientimpl.so');
  });
}

test('Global export lookup works when named linker export lookup misses', () => {
  const fallback = start('global');
  assert(fallback.hooks.has('__loader_dlopen'));
  assert(fallback.hooks.has('__loader_android_dlopen_ext'));
});

test('Missing inner exports are diagnosed without unsafe public-hook fallback', () => {
  const missing = start('missing');
  assert.equal(
    missing.logs.filter(value => value.startsWith('STARTUP_LOADER_HOOK_UNAVAILABLE')).length,
    2,
  );
  assert(!missing.hooks.has('dlopen'));
  assert(!missing.hooks.has('android_dlopen_ext'));
});

test('Both successful hook installations have a device-verifiable marker', () => {
  assert.equal(
    run.logs.filter(value => value.startsWith('STARTUP_LOADER_HOOK_READY')).length,
    2,
  );
});

console.log(JSON.stringify({
  method: 'Actual source with mocked Frida APIs, not Android runtime',
  passed: tests.length,
  tests,
}, null, 2));
