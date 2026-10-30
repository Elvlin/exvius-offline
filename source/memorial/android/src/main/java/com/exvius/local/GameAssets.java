package com.exvius.local;

import android.content.Context;
import android.content.res.Resources;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import java.io.File;
import java.util.Collections;
import java.util.Set;
import java.util.WeakHashMap;

/** Make downloaded original assets available to the original Java and native readers. */
public final class GameAssets {
    private static final Set<Resources> attached = Collections.newSetFromMap(new WeakHashMap<>());
    private GameAssets() {}

    public static File archive(Context context) {
        return new File(DataUpdates.dataRoot(context), "client/game-assets.apk");
    }

    public static synchronized void attach(Context context) {
        Resources resources = context.getResources();
        if (attached.contains(resources)) return;
        File archive = archive(context);
        if (!archive.isFile()) throw new IllegalStateException("Download the game data before starting the game.");
        try {
            if (Build.VERSION.SDK_INT >= 30) Modern.attach(resources, archive);
            else {
                // The original Android AssetManager API on Android 7-10.
                java.lang.reflect.Method add = android.content.res.AssetManager.class
                    .getMethod("addAssetPath", String.class);
                if (((Integer) add.invoke(context.getAssets(), archive.getPath())) == 0)
                    throw new java.io.IOException("Cannot open downloaded game assets");
            }
            attached.add(resources);
        } catch (Exception error) {
            throw new IllegalStateException("Cannot open the installed game data.", error);
        }
    }

    @android.annotation.TargetApi(30)
    private static final class Modern {
        static void attach(Resources resources, File archive) throws java.io.IOException {
            android.content.res.loader.ResourcesLoader loader = new android.content.res.loader.ResourcesLoader();
            try (ParcelFileDescriptor descriptor = ParcelFileDescriptor.open(archive, ParcelFileDescriptor.MODE_READ_ONLY)) {
                loader.addProvider(android.content.res.loader.ResourcesProvider.loadFromApk(descriptor));
            }
            resources.addLoaders(loader);
        }
    }
}
