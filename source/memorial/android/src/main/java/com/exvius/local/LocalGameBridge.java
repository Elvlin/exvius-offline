package com.exvius.local;

import android.content.Context;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.util.LinkedHashMap;
import java.util.Map;
import org.json.JSONObject;

public final class LocalGameBridge {
    private static Context context;
    private static PyObject module;
    private static PyObject game;

    private LocalGameBridge() {}

    static synchronized void initialize(Context value) {
        context = value;
        DataUpdates.initialize(context);
        android.app.job.JobScheduler jobs = (android.app.job.JobScheduler)
            context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (jobs != null) {
            for (android.app.job.JobInfo job : jobs.getAllPendingJobs()) {
                String service = job.getService().getClassName();
                if (service.startsWith("com.google.") || service.startsWith("androidx.work."))
                    jobs.cancel(job.getId());
            }
        }
    }

    public static boolean handles(String address) {
        try {
            URL url = new URL(address);
            return "http".equalsIgnoreCase(url.getProtocol()) ||
                "https".equalsIgnoreCase(url.getProtocol());
        } catch (Exception error) {
            return false;
        }
    }

    public static HttpURLConnection openConnection(String address) throws IOException {
        if (!handles(address)) throw new IOException("Not a local game request");
        return new LocalGameConnection(new URL(address));
    }

    public static HttpURLConnection openConnection(URL address) throws IOException {
        return openConnection(address.toString());
    }

    public static java.io.InputStream openStream(URL address) throws IOException {
        return openConnection(address).getInputStream();
    }

    public static int localDataState() {
        return context != null && context.getFilesDir().isDirectory() ? 1 : 0;
    }

    public static void installAssets(Context owner) { GameAssets.attach(owner); }

    public static String gameAssetsPath() { return GameAssets.archive(context).getAbsolutePath(); }

    public static void setLocalMediaSource(android.media.MediaPlayer player, Context owner,
                                            android.net.Uri address) throws IOException {
        String scheme = address.getScheme();
        if (scheme == null || "file".equalsIgnoreCase(scheme) ||
                "content".equalsIgnoreCase(scheme) || "android.resource".equalsIgnoreCase(scheme)) {
            player.setDataSource(owner, address);
            return;
        }
        File file = localFile(address.getPath());
        if (file == null) throw new IOException("Local movie file is unavailable");
        try (java.io.FileInputStream input = new java.io.FileInputStream(file)) {
            player.setDataSource(input.getFD());
        }
    }

    public static void configureWebView(android.webkit.WebView view) {
        android.webkit.WebSettings settings = view.getSettings();
        settings.setBlockNetworkLoads(true);
        if (android.os.Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(false);
    }

    static File localFile(String path) throws IOException {
        if (context == null) return null;
        File root = context.getFilesDir().getCanonicalFile();
        String relative = android.net.Uri.decode(path);
        while (relative.startsWith("/")) relative = relative.substring(1);
        if (relative.startsWith("banner/")) relative = relative.substring(7);
        File file = new File(root, relative).getCanonicalFile();
        if (!file.getPath().startsWith(root.getPath() + File.separator))
            throw new IOException("Invalid local resource path");
        if (file.isFile()) return file;
        if (relative.startsWith("en/sd/static_banner/marquee/")) {
            file = new File(new File(root, "homeMarquee"), new File(relative).getName());
            if (file.isFile()) return file;
        }
        return null;
    }

    public static boolean existingFile(String address, String destination) {
        try {
            File source = localFile(new URL(address).getPath());
            return source != null && source.length() > 0 &&
                source.getCanonicalFile().equals(new File(destination).getCanonicalFile());
        } catch (IOException error) {
            return false;
        }
    }

    // A native file the installer still lacks: let the local engine produce it
    // from the bundled content (art by name, overlays, versioned tables).
    // Written atomically; false leaves the original missing-file path in place.
    public static synchronized boolean materializeFile(String address, String destination) {
        try {
            Response response = request("GET", new URL(address).getPath(), new byte[0],
                                        new java.util.HashMap<>());
            if (response.status != 200 || response.body.length == 0) return false;
            File target = new File(destination);
            File parent = target.getParentFile();
            if (parent != null && !parent.isDirectory() && !parent.mkdirs()) return false;
            File partial = new File(destination + ".local");
            try (java.io.FileOutputStream out = new java.io.FileOutputStream(partial)) {
                out.write(response.body);
            }
            return partial.renameTo(target);
        } catch (IOException | RuntimeException error) {
            return false;
        }
    }

    public static synchronized String materializedPath(String relative) {
        try {
            File existing = localFile(relative);
            if (existing != null) return existing.getAbsolutePath();
            if (context == null) return "";
            while (relative.startsWith("/")) relative = relative.substring(1);
            File root = context.getFilesDir().getCanonicalFile();
            File target = new File(root, relative).getCanonicalFile();
            if (!target.getPath().startsWith(root.getPath() + File.separator)) return "";
            return materializeFile("http://127.0.0.1/" + relative, target.getPath())
                ? target.getPath() : "";
        } catch (IOException error) {
            return "";
        }
    }

    public static android.webkit.WebResourceResponse webResource(String address) {
        if (!handles(address)) return null;
        try {
            HttpURLConnection connection = openConnection(address);
            int status = connection.getResponseCode();
            String mime = URLConnection.guessContentTypeFromName(new URL(address).getPath());
            if (mime == null) mime = "application/octet-stream";
            java.io.InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream == null) stream = new ByteArrayInputStream(new byte[0]);
            return new android.webkit.WebResourceResponse(mime, "UTF-8", status,
                status == 200 ? "OK" : "Local data unavailable", new LinkedHashMap<>(), stream);
        } catch (Exception error) {
            android.util.Log.e("ExviusLocal", "Local web resource failed", error);
            return new android.webkit.WebResourceResponse("text/plain", "UTF-8", 500,
                "Local data unavailable", new LinkedHashMap<>(), new ByteArrayInputStream(new byte[0]));
        }
    }

    public static void postLocalPage(android.webkit.WebView view, String address, byte[] body) {
        // WebView resource interception does not carry a POST body. Dispatch it
        // through the existing local handler before giving the page to WebView.
        new Thread(() -> {
            try {
                HttpURLConnection connection = openConnection(address);
                connection.setRequestMethod("POST");
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                connection.getOutputStream().write(body);
                if (connection.getResponseCode() >= 400)
                    throw new IOException("Local page status " + connection.getResponseCode());
                String html;
                try (java.io.InputStream input = connection.getInputStream()) {
                    java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
                    byte[] buffer = new byte[8192];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                    html = output.toString("UTF-8");
                }
                final String page = html;
                view.post(() -> view.loadDataWithBaseURL(address, page, "text/html", "UTF-8", null));
            } catch (Exception error) {
                android.util.Log.e("ExviusLocal", "Local page failed", error);
                // Keep the original game's error callback and loading lifecycle.
                view.post(() -> {
                    if (android.os.Build.VERSION.SDK_INT >= 26)
                        view.getWebViewClient().onReceivedError(view, -1,
                            "Unable to load local game data.", address);
                    else view.loadDataWithBaseURL(address,
                        "<html><body>Unable to load local game data.</body></html>",
                        "text/html", "UTF-8", null);
                });
            }
        }, "ExviusLocalPage").start();
    }

    public static synchronized String summonArchive(String selection) {
        if (game == null) throw new IllegalStateException("Open the local game before selecting summons");
        return module.callAttr("summon_archive", game, selection).toString();
    }

    public static synchronized String eventArchive(String selection) {
        if (game == null) throw new IllegalStateException("Open the local game before selecting events");
        return module.callAttr("event_archive", game, selection).toString();
    }

    public static synchronized boolean raidAction(String actor, int skill, String party) {
        if (game == null) return false;
        return module.callAttr("raid_action", game, actor, skill, party).toBoolean();
    }

    private static void ensureGame() {
        if (game != null) return;
        if (context == null) throw new IllegalStateException("Local game provider is not ready");
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        module = Python.getInstance().getModule("android_game");
        if (!DataUpdates.ready(context)) throw new IllegalStateException("Game data installation is not complete");
        game = module.callAttr("start", new File(context.getFilesDir(), "exvius").getPath(),
            DataUpdates.dataRoot(context).getPath());
    }

    // Title Continue/New Game: "status" or "new" (backs up the save, then starts fresh).
    public static synchronized String titleAction(String action) {
        ensureGame();
        return module.callAttr("title_action", game, action).toString();
    }

    static synchronized Response request(String method, String path, byte[] body,
                                          Map<String, String> headers) throws IOException {
        try {
            ensureGame();
            PyObject result = module.callAttr("request", game, method, path, body,
                                               new JSONObject(headers).toString());
            Map<String, String> responseHeaders = new LinkedHashMap<>();
            for (Map.Entry<PyObject, PyObject> entry : result.get("headers").asMap().entrySet()) {
                responseHeaders.put(entry.getKey().toString(), entry.getValue().toString());
            }
            int status = result.get("status").toInt();
            if (status >= 400) {
                String resource = path.split("\\?", 2)[0];
                android.util.Log.w("ExviusLocal", "Local content unavailable: " +
                    status + " " + method + " " + resource);
            }
            return new Response(status, responseHeaders,
                                result.get("body").toJava(byte[].class));
        } catch (RuntimeException error) {
            throw new IOException("The local game request failed", error);
        }
    }

    static final class Response {
        final int status;
        final Map<String, String> headers;
        final byte[] body;
        Response(int code, Map<String, String> fields, byte[] content) {
            status = code;
            headers = fields;
            body = content;
        }
    }
}
