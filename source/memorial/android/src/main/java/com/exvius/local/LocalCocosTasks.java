package com.exvius.local;

import android.os.Handler;
import android.os.Looper;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;

/** Supplies the original Cocos task callbacks from local files and game data. */
public final class LocalCocosTasks {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Map<Object, Set<Thread>> ACTIVE = new IdentityHashMap<>();

    private LocalCocosTasks() {}

    // The original Cocos classes are retained in the client DEX, rather than
    // copied into the embedded runtime. Reflection crosses that DEX boundary.
    private static void callback(Object owner, String name, Class<?>[] types, Object... values) {
        try {
            Method method = owner.getClass().getDeclaredMethod(name, types);
            method.setAccessible(true);
            method.invoke(owner, values);
        } catch (ReflectiveOperationException error) {
            throw new IllegalStateException("Original local loading callback failed: " + name, error);
        }
    }

    private static void progress(Object owner, int id, long delta, long total, long expected) {
        MAIN.post(() -> callback(owner, "onProgress",
            new Class<?>[]{int.class, long.class, long.class, long.class}, id, delta, total, expected));
    }

    public static void load(Object owner, int id, String address, String destination) {
        Thread worker = new Thread(() -> {
            int code = 0;
            String message = "";
            byte[] result = null;
            File staging = null;
            MAIN.post(() -> callback(owner, "onStart", new Class<?>[]{int.class}, id));
            try {
                java.net.HttpURLConnection connection = LocalGameBridge.openConnection(address);
                if (connection.getResponseCode() >= 400)
                    throw new IOException("Local resource status " + connection.getResponseCode());
                long expected = connection.getContentLengthLong();
                if (!destination.isEmpty() && LocalGameBridge.existingFile(address, destination)) {
                    progress(owner, id, 0, expected, expected);
                } else {
                    File target = destination.isEmpty() ? null : new File(destination).getCanonicalFile();
                    ByteArrayOutputStream bytes = target == null ? new ByteArrayOutputStream() : null;
                    if (target != null) {
                        File parent = target.getParentFile();
                        if (!parent.isDirectory() && !parent.mkdirs())
                            throw new IOException("Unable to prepare the local resource directory");
                        staging = File.createTempFile(".exvius-load-", ".tmp", parent);
                    }
                    try (InputStream input = connection.getInputStream();
                         OutputStream output = target == null ? bytes : new FileOutputStream(staging)) {
                        byte[] buffer = new byte[65536];
                        long total = 0, reported = 0;
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            if (Thread.currentThread().isInterrupted())
                                throw new IOException("Local loading cancelled");
                            output.write(buffer, 0, count);
                            total += count;
                            if (total - reported >= 1048576) {
                                progress(owner, id, total - reported, total, expected);
                                reported = total;
                            }
                        }
                        if (expected >= 0 && total != expected)
                            throw new IOException("Incomplete local resource");
                        progress(owner, id, total - reported, total, expected);
                    }
                    if (Thread.currentThread().isInterrupted()) throw new IOException("Local loading cancelled");
                    if (target == null) result = bytes.toByteArray();
                    else if (!staging.renameTo(target)) throw new IOException("Unable to store the local resource");
                }
            } catch (Exception error) {
                code = -1;
                message = error.getMessage() == null ? "Unable to load local game data." : error.getMessage();
            } finally {
                if (staging != null) staging.delete();
                synchronized (ACTIVE) {
                    Set<Thread> workers = ACTIVE.get(owner);
                    if (workers != null) {
                        workers.remove(Thread.currentThread());
                        if (workers.isEmpty()) ACTIVE.remove(owner);
                    }
                }
                final int status = code;
                final String detail = message;
                final byte[] content = result;
                MAIN.post(() -> {
                    callback(owner, "onFinish", new Class<?>[]{int.class, int.class, String.class, byte[].class},
                        id, status, detail, content);
                    callback(owner, "runNextTaskIfExists", new Class<?>[0]);
                });
            }
        }, "ExviusLocalFile");
        synchronized (ACTIVE) {
            ACTIVE.computeIfAbsent(owner, key -> Collections.newSetFromMap(new IdentityHashMap<>())).add(worker);
        }
        worker.start();
    }

    public static void cancel(Object owner) {
        // Called by the original UI-thread cancellation runnable.
        try {
            java.lang.reflect.Field field = owner.getClass().getDeclaredField("_taskQueue");
            field.setAccessible(true);
            ((java.util.Queue<?>) field.get(owner)).clear();
        } catch (ReflectiveOperationException error) {
            throw new IllegalStateException("Original local loading queue is unavailable", error);
        }
        synchronized (ACTIVE) {
            Set<Thread> workers = ACTIVE.get(owner);
            if (workers != null) for (Thread worker : workers) worker.interrupt();
        }
    }
}
