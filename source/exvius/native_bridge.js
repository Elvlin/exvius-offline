// Use the original game's JNI helper for calls from native game callbacks.
// Keep each JNIEnv and its local references on the current native thread.
// Let ART handle its own native signals. Frida's default exception stealing
// unwinds native calls and can leave a Java transition in an invalid state.
export function createNativeBridge(module) {
  const methodInfo = new NativeFunction(module.getExportByName(
    '_ZN7cocos2d9JniHelper19getStaticMethodInfoERNS_14JniMethodInfo_EPKcS4_S4_'),
    'bool', ['pointer', 'pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  const className = Memory.allocUtf8String('com/exvius/local/LocalGameBridge');
  return function call(method, signature, args, result = 'string') {
    const info = Memory.alloc(Process.pointerSize * 3);
    if (!methodInfo(info, className, Memory.allocUtf8String(method), Memory.allocUtf8String(signature)))
      throw new Error('Local method is unavailable: ' + method);
    const env = info.readPointer(), cls = info.add(Process.pointerSize).readPointer();
    const methodId = info.add(Process.pointerSize * 2).readPointer(), table = env.readPointer();
    const jni = (index, type, parameters) => new NativeFunction(
      table.add(index * Process.pointerSize).readPointer(), type, parameters, {exceptions: 'propagate'});
    const newString = jni(167, 'pointer', ['pointer', 'pointer']);
    const invoke = jni(result === 'string' ? 116 : 119, result === 'string' ? 'pointer' : 'bool',
      ['pointer', 'pointer', 'pointer', 'pointer']);
    const getChars = jni(169, 'pointer', ['pointer', 'pointer', 'pointer']);
    const releaseChars = jni(170, 'void', ['pointer', 'pointer', 'pointer']);
    const deleteRef = jni(23, 'void', ['pointer', 'pointer']);
    const hasException = jni(228, 'bool', ['pointer']);
    const clearException = jni(17, 'void', ['pointer']);
    const refs = [cls], values = Memory.alloc(Math.max(8, args.length * 8));
    values.writeByteArray(new Uint8Array(Math.max(8, args.length * 8)));
    let output = ptr(0), text = ptr(0);
    function check() {
      if (!hasException(env)) return;
      clearException(env);
      throw new Error('Local method failed: ' + method);
    }
    try {
      for (let i = 0; i < args.length; i++) {
        const value = args[i];
        if (typeof value === 'string') {
          const string = newString(env, Memory.allocUtf8String(value));
          check();
          if (string.isNull()) throw new Error('Local argument allocation failed');
          refs.push(string);
          values.add(i * 8).writePointer(string);
        } else if (Number.isInteger(value) && value >= -2147483648 && value <= 2147483647)
          values.add(i * 8).writeS32(value);
        else throw new Error('Invalid local method argument');
      }
      const returned = invoke(env, cls, methodId, values);
      check();
      if (result !== 'string') return Boolean(returned);
      output = returned;
      if (output.isNull()) throw new Error('Local method returned no text');
      refs.push(output);
      text = getChars(env, output, ptr(0));
      check();
      if (text.isNull()) throw new Error('Local text is unavailable');
      return text.readUtf8String();
    } finally {
      if (!text.isNull()) releaseChars(env, output, text);
      for (const ref of refs.reverse()) if (!ref.isNull()) deleteRef(env, ref);
    }
  };
}
