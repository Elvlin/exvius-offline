import Java from '../../tools/vendor/android-agent/node_modules/frida-java-bridge/index.js';

// Keep the client's existing request creation and response handling. Only its
// game connections are supplied by the embedded, existing gameplay runtime.
Java.perform(() => {
    const bridge = Java.use('com.exvius.local.LocalGameBridge');
    // The game-owned callers use the bridge directly in their Java source.
    // Route any remaining library URL access locally as well.
    const url = Java.use('java.net.URL');
    const open = url.openConnection.overload();
    open.implementation = function () {
        const address = this.toString();
        if (bridge.handles(address)) return bridge.openConnection(address);
        return open.call(this);
    };
    const proxyOpen = url.openConnection.overload('java.net.Proxy');
    proxyOpen.implementation = function (proxy) {
        const address = this.toString();
        if (bridge.handles(address)) return bridge.openConnection(address);
        return proxyOpen.call(this, proxy);
    };
    console.log('EXVIUS_LOCAL_CONNECTION_READY');
});
