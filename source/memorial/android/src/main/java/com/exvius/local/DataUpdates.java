package com.exvius.local;

import android.app.Activity;
import android.app.Application;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.ref.WeakReference;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/** One complete first download, cached offline play, and static release updates. */
public final class DataUpdates {
    private static final String LATEST = "https://raw.githubusercontent.com/Elvlin/exvius-offline/main/data/latest.json";
    private static final String ASSETS = "https://github.com/Elvlin/exvius-offline/releases/download/";
    private static final AtomicBoolean working = new AtomicBoolean();
    private static volatile Progress listener;
    private static WeakReference<Activity> foreground = new WeakReference<>(null);
    private static boolean initialized, gameOpened, permissionPrompted, installerShown;

    public interface Progress {
        void update(String message, long done, long total);
        void complete();
        void failed(String message);
    }
    private DataUpdates() {}

    static synchronized void initialize(Context context) {
        if (initialized) return;
        initialized = true;
        ((Application) context.getApplicationContext()).registerActivityLifecycleCallbacks(
            new Application.ActivityLifecycleCallbacks() {
                public void onActivityResumed(Activity activity) {
                    foreground = new WeakReference<>(activity);
                    maybeInstall(activity);
                }
                public void onActivityPaused(Activity activity) {
                    if (foreground.get() == activity) foreground.clear();
                }
                public void onActivityCreated(Activity activity, Bundle state) {
                    if (activity.getClass().getName().equals("com.square_enix.android_googleplay.FFBEWW.Lapis"))
                        gameOpened = true;
                }
                public void onActivityStarted(Activity activity) {}
                public void onActivityStopped(Activity activity) {}
                public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
                public void onActivityDestroyed(Activity activity) {}
            });
    }

    private static File state(Context context, String name) {
        return new File(context.getFilesDir(), "exvius/data/" + name);
    }
    public static File dataRoot(Context context) { return state(context, "static"); }
    public static boolean gameOpened() { return gameOpened; }
    public static boolean hasPending(Context context) { return state(context, "pending.json").isFile(); }
    public static boolean ready(Context context) {
        return state(context, "installed.json").isFile() &&
            new File(dataRoot(context), "mst_decoded/F_UNIT_MST.ndjson").isFile() &&
            new File(context.getFilesDir(), "mst").isDirectory();
    }
    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("offline_updates", Context.MODE_PRIVATE);
    }
    private static DownloadManager downloads(Context context) {
        return (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
    }
    private static boolean online(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
    private static int appVersion(Context context) throws Exception {
        return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionCode;
    }
    private static String read(File file) throws IOException {
        if (file.length() > 524288) throw new IOException("Update information is too large");
        try (FileInputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > 524288) throw new IOException("Update information is too large");
                output.write(buffer, 0, count);
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        }
    }
    private static void write(File file, String text) throws IOException {
        File parent = file.getParentFile();
        if (!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Cannot create update folder");
        File partial = new File(parent, file.getName() + ".new");
        try (FileOutputStream output = new FileOutputStream(partial)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        try {
            android.system.Os.rename(partial.getPath(), file.getPath());
        } catch (android.system.ErrnoException error) {
            throw new IOException("Cannot save update information", error);
        }
    }
    private static JSONObject installed(Context context) throws Exception {
        File file = state(context, "installed.json");
        return file.isFile() ? new JSONObject(read(file)) : new JSONObject();
    }
    private static boolean installedPack(JSONObject current, JSONObject pack) throws Exception {
        JSONArray packs = current.optJSONArray("packs");
        if (packs == null) return false;
        for (int i = 0; i < packs.length(); i++) {
            JSONObject row = packs.getJSONObject(i);
            if (pack.getString("id").equals(row.optString("id")) &&
                pack.getString("sha256").equals(row.optString("sha256"))) return true;
        }
        return false;
    }
    private static void validate(JSONObject manifest) throws Exception {
        if (manifest.getInt("schema") != 1 || manifest.getLong("revision") < 1)
            throw new IOException("Unsupported update information");
        JSONArray packs = manifest.getJSONArray("packs");
        if (packs.length() < 1 || packs.length() > 1000) throw new IOException("Invalid data pack list");
        java.util.HashSet<String> ids = new java.util.HashSet<>();
        for (int i = 0; i < packs.length(); i++) {
            JSONObject pack = packs.getJSONObject(i);
            if (!pack.getString("id").matches("[a-zA-Z0-9_-]{1,80}") || !ids.add(pack.getString("id")) ||
                !pack.getString("url").startsWith(ASSETS) ||
                !pack.getString("sha256").matches("[a-f0-9]{64}") ||
                pack.getLong("size") < 1 || pack.getLong("size") >= 2147483648L ||
                pack.getLong("unpackedSize") < 1)
                throw new IOException("Invalid data pack information");
        }
    }
    private static File downloadFile(Context context, String key, String suffix) throws IOException {
        File folder = context.getExternalFilesDir("updates");
        if (folder == null || (!folder.isDirectory() && !folder.mkdirs()))
            throw new IOException("Download storage is unavailable");
        return new File(folder, key + suffix);
    }
    private static void progress(String text, long done, long total) {
        Progress current = listener;
        if (current != null) current.update(text, done, total);
    }

    private static File download(Context context, String key, String url, String suffix,
                                 long base, long total, boolean small) throws Exception {
        DownloadManager manager = downloads(context);
        SharedPreferences saved = preferences(context);
        File target = downloadFile(context, key, suffix);
        String preference = "download_" + key;
        long id = saved.getLong(preference, -1);
        long deadline = small ? System.currentTimeMillis() + 20000 : Long.MAX_VALUE;
        for (;;) {
            if (id < 0) {
                if (target.exists() && !target.delete()) throw new IOException("Cannot restart download");
                boolean appUpdate = suffix.equals(".apk");
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url))
                    .setTitle(small ? "Exvius update check" : appUpdate ? "Exvius app update" : "Exvius game data")
                    .setDescription(small ? "Checking the latest version" : appUpdate ?
                        "Downloading the latest app version" : "Downloading the complete offline game data")
                    .setDestinationUri(Uri.fromFile(target));
                if (suffix.equals(".apk")) request.setMimeType("application/vnd.android.package-archive");
                id = manager.enqueue(request);
                saved.edit().putLong(preference, id).commit();
            }
            try (Cursor cursor = manager.query(new DownloadManager.Query().setFilterById(id))) {
                if (cursor == null || !cursor.moveToFirst()) {
                    saved.edit().remove(preference).commit();
                    id = -1;
                    continue;
                }
                int status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                long done = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                progress(small ? "Checking for game data..." : suffix.equals(".apk") ? "Downloading app update..." :
                    "Downloading game data: " + ((base + done) / 1048576) + " / " + (total / 1048576) + " MB",
                    base + Math.max(0, done), total);
                if (status == DownloadManager.STATUS_SUCCESSFUL) return target;
                if (status == DownloadManager.STATUS_FAILED) {
                    int reason = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
                    manager.remove(id);
                    saved.edit().remove(preference).commit();
                    throw new IOException(reason == DownloadManager.ERROR_INSUFFICIENT_SPACE ?
                        "Not enough free storage for the game data." : "The download could not finish. Check your connection and retry.");
                }
                if (System.currentTimeMillis() > deadline || (listener == null && !online(context)))
                    throw new IOException("Update check paused");
            }
            Thread.sleep(1000);
        }
    }
    private static File verifiedPack(Context context, JSONObject pack, long base, long total) throws Exception {
        String hash = pack.getString("sha256"), key = "data_" + hash;
        File file = download(context, key, pack.getString("url"), ".zip", base, total, false);
        File verified = downloadFile(context, key, ".verified");
        if (file.length() != pack.getLong("size")) {
            clearDownload(context, key, ".zip");
            throw new IOException("Downloaded file has the wrong size. Please retry.");
        }
        if (!verified.isFile() || !read(verified).equals(hash)) {
            progress("Checking downloaded game data...", base, total);
            if (!DataPack.sha256(file).equals(hash)) {
                downloads(context).remove(preferences(context).getLong("download_" + key, -1));
                preferences(context).edit().remove("download_" + key).commit();
                verified.delete();
                throw new IOException("Game data verification failed. Please retry.");
            }
            write(verified, hash);
        }
        return file;
    }
    private static void clearDownload(Context context, String key, String suffix) throws Exception {
        long id = preferences(context).getLong("download_" + key, -1);
        if (id >= 0) downloads(context).remove(id);
        preferences(context).edit().remove("download_" + key).commit();
        downloadFile(context, key, suffix).delete();
        downloadFile(context, key, ".verified").delete();
    }
    private static void installPending(Context context) throws Exception {
        JSONObject manifest = new JSONObject(read(state(context, "pending.json")));
        validate(manifest);
        JSONObject current = ready(context) ? installed(context) : new JSONObject();
        JSONArray packs = manifest.getJSONArray("packs");
        File journalFile = state(context, "install-progress.json");
        JSONObject journal = journalFile.isFile() ? new JSONObject(read(journalFile)) : new JSONObject();
        JSONArray completed = journal.optLong("revision") == manifest.getLong("revision") ?
            journal.optJSONArray("completed") : null;
        if (completed == null) completed = new JSONArray();
        java.util.HashSet<String> installedHashes = new java.util.HashSet<>();
        for (int i = 0; i < completed.length(); i++) installedHashes.add(completed.getString(i));
        long total = 0, transferred = 0;
        for (int i = 0; i < packs.length(); i++) total += packs.getJSONObject(i).getLong("size");
        for (int i = 0; i < packs.length(); i++) {
            JSONObject pack = packs.getJSONObject(i);
            if (installedPack(current, pack) || installedHashes.contains(pack.getString("sha256"))) {
                transferred += pack.getLong("size");
                continue;
            }
            File archive = downloadFile(context, "data_" + pack.getString("sha256"), ".zip");
            File verified = downloadFile(context, "data_" + pack.getString("sha256"), ".verified");
            if (!archive.isFile() || archive.length() != pack.getLong("size") || !verified.isFile() ||
                !read(verified).equals(pack.getString("sha256"))) {
                if (!archive.isFile() && !online(context))
                    throw new IOException("Connect to the internet to finish the game data installation.");
                archive = verifiedPack(context, pack, transferred, total);
            }
            progress("Installing game data (" + (i + 1) + "/" + packs.length() + ")...", i, packs.length());
            try {
                DataPack.extract(archive, context.getFilesDir(), pack.getLong("unpackedSize"));
            } catch (IOException error) {
                clearDownload(context, "data_" + pack.getString("sha256"), ".zip");
                throw new IOException("A game data pack could not be installed. Please retry.", error);
            }
            transferred += pack.getLong("size");
            completed.put(pack.getString("sha256"));
            journal.put("revision", manifest.getLong("revision")).put("completed", completed);
            write(journalFile, journal.toString());
            clearDownload(context, "data_" + pack.getString("sha256"), ".zip");
        }
        File registryFile = state(context, "registry.json");
        JSONObject registry = new JSONObject(read(registryFile));
        SharedPreferences.Editor registryEdit = context.getSharedPreferences("gamedata", Context.MODE_PRIVATE).edit();
        Iterator<String> keys = registry.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            if (!key.startsWith("keyF_")) throw new IOException("Invalid resource registry key");
            registryEdit.putString(key, registry.getString(key));
        }
        if (!registryEdit.commit()) throw new IOException("Cannot save game resource versions");
        if (!new File(dataRoot(context), "mst_decoded/F_UNIT_MST.ndjson").isFile())
            throw new IOException("The downloaded game data is incomplete");
        write(state(context, "installed.json"), manifest.toString());
        state(context, "pending.json").delete();
        journalFile.delete();
        for (int i = 0; i < packs.length(); i++)
            clearDownload(context, "data_" + packs.getJSONObject(i).getString("sha256"), ".zip");
    }
    public static void prepare(Context context, Progress progress) {
        listener = progress;
        begin(context.getApplicationContext(), true);
    }
    public static void detach(Progress progress) { if (listener == progress) listener = null; }
    public static synchronized void checkInBackground(Context context) {
        listener = null;
        begin(context.getApplicationContext(), false);
    }
    private static void begin(Context context, boolean mandatory) {
        if (!working.compareAndSet(false, true)) return;
        new Thread(() -> {
            try {
                if (hasPending(context)) {
                    if (!mandatory || gameOpened) return;
                    installPending(context);
                } else {
                    if (!online(context)) throw new IOException("Connect to the internet for the first game data download.");
                    File latest = download(context, "latest", LATEST, ".json", 0, 0, true);
                    JSONObject manifest = new JSONObject(read(latest));
                    validate(manifest);
                    clearDownload(context, "latest", ".json");
                    JSONObject current = ready(context) ? installed(context) : new JSONObject();
                    if (manifest.getInt("minAppVersionCode") <= appVersion(context) &&
                        (!ready(context) || manifest.getLong("revision") > current.optLong("revision"))) {
                        if (mandatory) {
                            // First installation needs space for only one downloaded part at a time.
                            write(state(context, "pending.json"), manifest.toString());
                            installPending(context);
                        } else {
                        JSONArray packs = manifest.getJSONArray("packs");
                        long total = 0, done = 0;
                        for (int i = 0; i < packs.length(); i++) {
                            JSONObject pack = packs.getJSONObject(i);
                            if (!installedPack(current, pack)) total += pack.getLong("size");
                        }
                        for (int i = 0; i < packs.length(); i++) {
                            JSONObject pack = packs.getJSONObject(i);
                            if (installedPack(current, pack)) continue;
                            verifiedPack(context, pack, done, total);
                            done += pack.getLong("size");
                        }
                        write(state(context, "pending.json"), manifest.toString());
                        // Running games keep their current files. Apply updates on the next launch.
                        }
                    }
                    JSONObject app = manifest.optJSONObject("app");
                    if (app != null && app.optInt("versionCode") > appVersion(context))
                        downloadApp(context, app);
                }
                Progress current = listener;
                if (mandatory && ready(context) && current != null) current.complete();
                else if (mandatory && current != null) current.failed("An app update is required. Install it and reopen Exvius.");
            } catch (Exception error) {
                android.util.Log.w("ExviusUpdates", "Update unavailable: " + error.getClass().getSimpleName());
                Progress current = listener;
                if (mandatory && current != null) current.failed(error.getMessage() == null ?
                    "Game data could not be downloaded. Please retry." : error.getMessage());
            } finally {
                listener = null;
                working.set(false);
            }
        }, "ExviusDataDownload").start();
    }
    private static void downloadApp(Context context, JSONObject app) throws Exception {
        String url = app.getString("url"), hash = app.getString("sha256");
        if (!url.startsWith(ASSETS) || !hash.matches("[a-f0-9]{64}")) throw new IOException("Invalid app update");
        File apk = download(context, "app_" + hash, url, ".apk", 0, app.getLong("size"), false);
        if (apk.length() != app.getLong("size") || !DataPack.sha256(apk).equals(hash)) {
            clearDownload(context, "app_" + hash, ".apk");
            throw new IOException("App update verification failed");
        }
        long id = preferences(context).getLong("download_app_" + hash, -1);
        preferences(context).edit().putLong("pending_apk", id).putInt("pending_apk_version", app.getInt("versionCode")).commit();
        Activity activity = foreground.get();
        if (activity != null) activity.runOnUiThread(() -> maybeInstall(activity));
    }
    private static void maybeInstall(Activity activity) {
        try {
            SharedPreferences saved = preferences(activity);
            long id = saved.getLong("pending_apk", -1);
            if (id < 0 || activity.isFinishing() || installerShown) return;
            if (saved.getInt("pending_apk_version", 0) <= appVersion(activity)) {
                downloads(activity).remove(id);
                saved.edit().remove("pending_apk").remove("pending_apk_version").commit();
                return;
            }
            if (android.os.Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) {
                if (!permissionPrompted) {
                    permissionPrompted = true;
                    activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + activity.getPackageName())));
                }
                return;
            }
            Uri uri = downloads(activity).getUriForDownloadedFile(id);
            if (uri == null) return;
            installerShown = true;
            activity.startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(uri,
                "application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
        } catch (Exception error) {
            android.util.Log.w("ExviusUpdates", "Android installer is unavailable");
        }
    }
}
