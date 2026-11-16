package com.exvius.local;

import android.app.Activity;
import android.content.Context;
import android.util.Log;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Process;
import android.util.AtomicFile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Slot selection is frozen before Lapis loads the game library. */
public final class SaveSlots {
    static final int LIMIT = 10;
    static final int NAME_LIMIT = 14;
    private static Context context;
    private static int selected;
    private static boolean restarting;
    static final String[] STORES = {"gamedata", "Cocos2dxPrefsFile", "auth"};

    private SaveSlots() {}

    public static boolean isRestartProcess() {
        try (FileInputStream in = new FileInputStream("/proc/self/cmdline")) {
            byte[] name = new byte[256]; int size = in.read(name);
            int end = 0; while (end < size && name[end] != 0) end++;
            return new String(name, 0, end, StandardCharsets.UTF_8).endsWith(":save_restart");
        } catch (IOException error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); throw new IllegalStateException("Unable to identify game process", error); }
    }

    static File state(Context c) { return new File(c.getFilesDir(), "exvius/state"); }
    static File index(Context c) { return new File(state(c), "slots/index.json"); }
    static File prefs(Context c) { return new File(c.getApplicationInfo().dataDir, "shared_prefs"); }

    public static synchronized void initialize(Context value) {
        if (selected != 0 || isRestartProcess()) return;
        context = value.getApplicationContext();
        try {
            recoverDelete(context);
            SaveTransferActivity.recover(context);
            JSONObject catalogue = catalogue(context);
            selected = catalogue.getInt("active");
        } catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error);
            // A broken catalogue must not fall through to a missing campaign and create a new player.
            throw new IllegalStateException("Unable to open save catalogue. Existing save files are preserved.", error);
        }
    }

    static synchronized JSONObject catalogue(Context c) throws Exception {
        File file = index(c);
        if (!file.exists() && !new File(file + ".bak").exists()) {
            JSONObject initial = new JSONObject().put("format", 1).put("active", 1)
                .put("slots", new JSONArray().put(new JSONObject().put("id", 1).put("label", "")));
            storeCatalogue(c, initial);
            return initial;
        }
        JSONObject result;
        try (InputStream in = new AtomicFile(file).openRead()) {
            result = new JSONObject(new String(read(in, 65536), StandardCharsets.UTF_8));
        }
        validateCatalogue(result);
        return result;
    }

    static void validateCatalogue(JSONObject value) throws Exception {
        if (!(value.get("format") instanceof Number) || ((Number)value.get("format")).doubleValue() != 1) throw new IOException("Unknown save catalogue");
        JSONArray slots = value.getJSONArray("slots"); Set<Integer> ids = new HashSet<>();
        if (slots.length() < 1 || slots.length() > LIMIT) throw new IOException("Invalid slot count");
        for (int i = 0; i < slots.length(); i++) {
            JSONObject slot = slots.getJSONObject(i); int id = slot.getInt("id");
            if (!(slot.get("id") instanceof Number) || ((Number)slot.get("id")).doubleValue() != id || id < 1 || id > LIMIT || !ids.add(id)) throw new IOException("Invalid slot identifier");
            if (!(slot.get("label") instanceof String)) throw new IOException("Invalid slot label");
        }
        int active = value.getInt("active");
        if (!(value.get("active") instanceof Number) || ((Number)value.get("active")).doubleValue() != active || !ids.contains(active)) throw new IOException("Missing selected slot");
    }

    static void storeCatalogue(Context c, JSONObject value) throws Exception {
        validateCatalogue(value);
        atomic(index(c), value.toString().getBytes(StandardCharsets.UTF_8));
    }

    static void atomic(File file, byte[] bytes) throws IOException {
        File parent = file.getParentFile();
        if (!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Unable to create save directory");
        AtomicFile target = new AtomicFile(file); FileOutputStream out = target.startWrite();
        try { out.write(bytes); out.getFD().sync(); target.finishWrite(out); }
        catch (IOException | RuntimeException error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); target.failWrite(out); throw error; }
    }

    static byte[] read(InputStream in, int limit) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] buffer = new byte[65536]; int n;
        while ((n = in.read(buffer)) != -1) {
            if (out.size() > limit - n) throw new IOException("Save entry is too large");
            out.write(buffer, 0, n);
        }
        return out.toByteArray();
    }

    static byte[] bytes(File file) throws IOException {
        if (!file.exists()) return null;
        try (InputStream in = new FileInputStream(file)) { return read(in, 64 * 1024 * 1024); }
    }

    static String suffix(int id) { return String.format(Locale.ROOT, "%03d", id); }
    static String storeName(String base, int id) { return id == 1 ? base : base + "_slot_" + suffix(id); }
    static File campaign(Context c, int id) {
        return new File(state(c), id == 1 ? "campaign.json" : "slots/" + suffix(id) + "/campaign.json");
    }
    static File keychain(Context c, int id) {
        return id == 1 ? new File(c.getFilesDir(), "LKCBK.dat")
            : new File(campaign(c, id).getParentFile(), "LKCBK.dat");
    }

    public static int active() {
        if (selected == 0) throw new IllegalStateException("Save selection was not initialized");
        return selected;
    }

    public static SharedPreferences gamePreferences(Context owner, String key) {
        return owner.getSharedPreferences(key.startsWith("keyF_") ? "gamedata" : storeName("gamedata", active()), 0);
    }
    public static SharedPreferences cocosPreferences(Context owner) {
        return owner.getSharedPreferences(storeName("Cocos2dxPrefsFile", active()), 0);
    }
    public static SharedPreferences accountPreferences(Context owner) {
        return owner.getSharedPreferences(storeName("auth", active()), 0);
    }

    static int unused(JSONObject catalogue) throws Exception {
        Set<Integer> ids = new HashSet<>(); JSONArray slots = catalogue.getJSONArray("slots");
        for (int i = 0; i < slots.length(); i++) ids.add(slots.getJSONObject(i).getInt("id"));
        for (int id = 1; id <= LIMIT; id++) if (!ids.contains(id)) return id;
        return 0;
    }
    static boolean allocated(JSONObject catalogue, int id) throws Exception {
        JSONArray slots = catalogue.getJSONArray("slots");
        for (int i = 0; i < slots.length(); i++) if (slots.getJSONObject(i).getInt("id") == id) return true;
        return false;
    }
    static void select(Context c, int id, boolean create) throws Exception {
        JSONObject catalogue = catalogue(c);
        if (!allocated(catalogue, id)) {
            if (!create || id != unused(catalogue)) throw new IOException("Save slot is unavailable");
            File directory = campaign(c, id).getParentFile();
            if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Unable to create save slot");
            // Empty stores stay absent. Never seed from another player or from content.
            catalogue.getJSONArray("slots").put(new JSONObject().put("id", id).put("label", "").put("awaiting_name", true));
        }
        catalogue.put("active", id); storeCatalogue(c, catalogue);
    }

    static String normalizedName(String value) {
        StringBuilder out = new StringBuilder();
        if (value != null) value.codePoints().filter(cp -> !Character.isISOControl(cp)).forEach(cp -> out.appendCodePoint(cp));
        String text = out.toString(); int begin = 0, end = text.length();
        while (begin < end && blank(text.codePointAt(begin))) begin += Character.charCount(text.codePointAt(begin));
        while (end > begin && blank(text.codePointBefore(end))) end -= Character.charCount(text.codePointBefore(end));
        text = text.substring(begin, end);
        return text;
    }
    static String cleanName(String value) {
        String text = normalizedName(value); int count = text.codePointCount(0, text.length());
        return count > NAME_LIMIT ? text.substring(0, text.offsetByCodePoints(0, NAME_LIMIT)) : text;
    }
    private static boolean blank(int cp) { return Character.isWhitespace(cp) || Character.isSpaceChar(cp); }
    static String playerName(byte[] campaign) throws Exception {
        if (campaign == null) return "New save";
        JSONObject root = new JSONObject(new String(campaign, StandardCharsets.UTF_8));
        String name = cleanName(root.getJSONObject("identity").getString("handle_name"));
        return name.isEmpty() ? "New save" : name;
    }
    static JSONObject row(JSONObject catalogue, int id) throws Exception {
        JSONArray rows = catalogue.getJSONArray("slots");
        for (int i = 0; i < rows.length(); i++) if (rows.getJSONObject(i).getInt("id") == id) return rows.getJSONObject(i);
        throw new IOException("Profile is unavailable");
    }
    static String profileName(Context c, JSONObject row) throws Exception {
        int id = row.getInt("id"); String label = cleanName(row.getString("label"));
        // MS1 wrote only these generated labels. They are not player-authored renames.
        if (!label.isEmpty() && (row.optBoolean("renamed", false) || !label.equals("Slot " + id))) return label;
        String name = playerName(bytes(campaign(c, id)));
        boolean newlyCreated = row.optBoolean("awaiting_name", false) || (id > 1 && row.getString("label").equals("Slot " + id));
        if (newlyCreated && name.equals("Rain")) {
            byte[] bytes = bytes(campaign(c, id));
            if (bytes == null || !hasPlayerName(bytes)) return "New save";
        }
        return name;
    }
    static String profileName(Context c, int id) throws Exception { return profileName(c, row(catalogue(c), id)); }
    static void rename(Context c, int id, String value) throws Exception {
        String name = normalizedName(value);
        if (name.isEmpty()) throw new IOException("Enter a profile name");
        if (name.codePointCount(0, name.length()) > NAME_LIMIT) throw new IOException("Use up to " + NAME_LIMIT + " characters");
        JSONObject catalogue = catalogue(c); row(catalogue, id).put("label", name).put("renamed", true);
        storeCatalogue(c, catalogue);
    }
    static JSONObject profileChoices(Context c) throws Exception {
        JSONObject catalogue = catalogue(c); JSONArray profiles = new JSONArray(), rows = catalogue.getJSONArray("slots");
        for (int i = 0; i < rows.length(); i++) {
            JSONObject saved = rows.getJSONObject(i); int id = saved.getInt("id");
            profiles.put(new JSONObject().put("id", id).put("label", profileName(c, saved)));
        }
        return new JSONObject().put("profiles", profiles).put("free", unused(catalogue));
    }
    static JSONObject dropdownModel(Context c) throws Exception {
        JSONObject choices = profileChoices(c); JSONArray profiles = choices.getJSONArray("profiles"), rows = new JSONArray();
        for (int i = 0; i < profiles.length(); i++) {
            JSONObject profile = profiles.getJSONObject(i); int id = profile.getInt("id");
            rows.put(new JSONObject().put("action", "switch").put("id", id).put("label", profile.getString("label")).put("active", id == active()));
        }
        return new JSONObject().put("name", profileName(c, active())).put("rows", rows).put("new_id", choices.getInt("free"));
    }

    static JSONArray deleteChoices(Context c) throws Exception {
        JSONArray all = profileChoices(c).getJSONArray("profiles"), result = new JSONArray();
        int loaded = active();
        for (int i = 0; i < all.length(); i++) if (all.getJSONObject(i).getInt("id") != loaded) result.put(all.getJSONObject(i));
        return result;
    }
    static File deleteJournal(Context c) { return new File(state(c), "slots/delete.json"); }
    static void deleteCheckpoint(int point) throws IOException { /* JVM interruption injection in test copies only. */ }
    static void deleteFile(File file) throws IOException {
        if (file.exists() && !file.delete()) throw new IOException("Unable to delete profile file");
    }
    static void prepareDelete(Context c, int id, boolean confirmed) throws Exception {
        JSONObject catalogue = catalogue(c);
        if (!confirmed) throw new IOException("Deletion was not confirmed");
        if (id == active() || id == catalogue.getInt("active")) throw new IOException("The loaded profile cannot be deleted");
        row(catalogue, id);
        if (deleteJournal(c).exists() || SaveTransferActivity.journal(c).exists()) throw new IOException("Save management is already pending");
        // The numeric folder is a player-only home. Refuse an unexpected child before changing files.
        if (id > 1) {
            File[] children = campaign(c, id).getParentFile().listFiles();
            if (children != null) for (File child : children) {
                String n = child.getName();
                if (!n.matches("(campaign\\.json|LKCBK\\.dat)(\\.tmp|\\.new|\\.bak)?") || child.isDirectory())
                    throw new IOException("Unexpected file in profile folder; files preserved");
            }
        }
        JSONArray keep = new JSONArray(), slots = catalogue.getJSONArray("slots");
        for (int i = 0; i < slots.length(); i++) if (slots.getJSONObject(i).getInt("id") != id) keep.put(slots.getJSONObject(i));
        catalogue.put("slots", keep); validateCatalogue(catalogue);
        atomic(deleteJournal(c), new JSONObject().put("slot", id).put("catalogue", catalogue).toString().getBytes(StandardCharsets.UTF_8));
    }
    static synchronized void recoverDelete(Context c) throws Exception {
        File journal = deleteJournal(c);
        if (new File(journal + ".bak").exists()) try (InputStream ignored = new AtomicFile(journal).openRead()) {}
        if (!journal.exists()) return;
        JSONObject transaction = new JSONObject(new String(bytes(journal), StandardCharsets.UTF_8));
        int id = transaction.getInt("slot"); JSONObject next = transaction.getJSONObject("catalogue");
        validateCatalogue(next);
        if (id < 1 || id > LIMIT || id == selected || id == next.getInt("active") || allocated(next, id)
                || id == catalogue(c).getInt("active")) throw new IOException("The loaded profile cannot be deleted");
        deleteCheckpoint(0);
        File[] targets = SaveTransferActivity.targets(c, id);
        for (int i = 0; i < targets.length; i++) {
            // Profile 1 shares gamedata with installation-owned keyF_* resource versions.
            if (id == 1 && i == 1) atomic(targets[i], SaveTransferActivity.gamePreferences(null, bytes(targets[i])));
            else deleteFile(targets[i]);
            deleteFile(new File(targets[i] + ".bak")); deleteFile(new File(targets[i] + ".new")); deleteFile(new File(targets[i] + ".tmp"));
            deleteCheckpoint(i + 1);
        }
        if (id > 1) deleteFile(campaign(c, id).getParentFile());
        storeCatalogue(c, next); deleteCheckpoint(6);
        deleteFile(journal);
    }
    static boolean hasPlayerName(byte[] campaign) throws Exception {
        // CreateUserScene::updateEvent 0x26ee59c-0x26ee600 sets NEW_USER_SWITCH_ID
        // after create-user succeeds. F_DEFINE_MST maps it to 10000152;
        // F_SWITCH_MST maps that id to saved bucket 10, bit 55.
        JSONObject root = new JSONObject(new String(campaign, StandardCharsets.UTF_8));
        JSONObject progress = root.optJSONObject("progress");
        JSONObject switches = progress == null ? null : progress.optJSONObject("switches");
        if (switches == null || !switches.has("10")) return false;
        JSONArray bits = switches.getJSONArray("10");
        for (int i = 0; i < bits.length(); i++) if (bits.getInt(i) == 55) return true;
        return false;
    }

    static Activity activity() throws Exception {
        Object value = Class.forName("org.cocos2dx.lib.Cocos2dxActivity").getMethod("getContext").invoke(null);
        if (!(value instanceof Activity)) throw new IOException("Game activity is unavailable");
        return (Activity)value;
    }
    static void gameThread(Runnable task) throws Exception {
        Class.forName("org.cocos2dx.lib.Cocos2dxHelper").getMethod("runOnGLThread", Runnable.class).invoke(null, task);
    }
    static void error(Activity a, String message) { SaveTransferActivity.message("Save management", message); }

    public static String titleProfiles() {
        try { return dropdownModel(context).toString(); }
        catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); return ""; }
    }
    public static boolean profileAction(String action, String identifier) {
        try {
            Activity a = activity(); int id = Integer.parseInt(identifier);
            if (action.equals("new") && id == unused(catalogue(a))) restart(a, id, true, false);
            else if (action.equals("switch") && allocated(catalogue(a), id)) { if (id != active()) restart(a, id, false, false); }
            else return false;
            return true;
        } catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); return false; }
    }
    static native void refreshTitle();

    public static String titleInsets() {
        try {
            android.view.View content = activity().findViewById(android.R.id.content);
            android.view.WindowInsets insets = content.getRootWindowInsets(); int[] position = new int[2]; content.getLocationOnScreen(position);
            int top = 0;
            if (insets != null) {
                top = Math.max(insets.getSystemWindowInsetTop(), insets.getStableInsetTop());
                if (android.os.Build.VERSION.SDK_INT >= 28 && insets.getDisplayCutout() != null) top = Math.max(top, insets.getDisplayCutout().getSafeInsetTop());
            }
            return new JSONObject().put("top", Math.max(0, top - position[1])).put("height", content.getHeight()).toString();
        } catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); return ""; }
    }

    static void flushPreferences(Context c) throws IOException {
        for (String base : STORES) {
            String name = storeName(base, active());
            if (new File(prefs(c), name + ".xml").exists() && !c.getSharedPreferences(name, 0).edit().commit())
                throw new IOException("Unable to flush save preferences");
        }
    }

    /** Called from native capture while the game thread and state lock are held. */
    public static byte[][] captureClient() throws Exception {
        flushPreferences(context); byte[][] result = new byte[5][];
        for (int i = 0; i < STORES.length; i++) result[i + 1] = bytes(new File(prefs(context), storeName(STORES[i], active()) + ".xml"));
        result[4] = bytes(keychain(context, active())); return result;
    }
    static native byte[][] capture();
    static native boolean recognize(byte[] campaign);

    static void restart(Activity a, int destination, boolean create, boolean importing) {
        restart(a, destination, create, importing, false);
    }
    static void restart(Activity a, int destination, boolean create, boolean importing, boolean deleting) {
        synchronized (SaveSlots.class) { if (restarting) return; restarting = true; }
        try {
            Runnable handoff = () -> {
                try {
                    flushPreferences(a);
                    Intent intent = new Intent(a, SaveRestartActivity.class).putExtra("pid", Process.myPid())
                        .putExtra("slot", destination).putExtra("create", create).putExtra("import", importing).putExtra("delete", deleting)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
                    a.runOnUiThread(() -> {
                        try { a.startActivity(intent); }
                        catch (RuntimeException error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); synchronized (SaveSlots.class) { restarting = false; } error(a, "Unable to restart game"); }
                    });
                } catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); synchronized (SaveSlots.class) { restarting = false; } error(a, "Unable to prepare save switch"); }
            };
            // Cross the game-thread barrier before doing preference I/O on the worker.
            if (a instanceof SaveTransferActivity) new Thread(handoff, "SaveSwitch").start();
            else gameThread(() -> new Thread(handoff, "SaveSwitch").start());
        } catch (Exception error) { Log.e("SaveSlots", "SaveSlots handled " + error.getClass().getName() + ": " + error.getMessage(), error); synchronized (SaveSlots.class) { restarting = false; } error(a, "Unable to reach game thread"); }
    }
}
