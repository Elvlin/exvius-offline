package com.exvius.local;

import android.Manifest;
import android.app.Activity;
import android.content.ContentValues;
import android.content.Context;
import android.util.Log;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.*;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.json.*;
import org.w3c.dom.*;

/** Explicit save allowlist, opaque campaign bytes and recoverable stopped-process installation. */
public final class SaveTransferActivity extends Activity {
    static final String[] ENTRIES = {"campaign.json", "client/gamedata.xml", "client/Cocos2dxPrefsFile.xml", "client/auth.xml", "client/LKCBK.dat"};
    static final int ENTRY_LIMIT = 64 * 1024 * 1024;
    private static final int PICK_IMPORT = 831;
    private static final ExecutorService worker = Executors.newSingleThreadExecutor();
    private static final java.util.concurrent.ConcurrentLinkedQueue<String> events = new java.util.concurrent.ConcurrentLinkedQueue<>();
    private static volatile boolean busy;
    private static Archive imported;

    static void logged(Exception error) {
        Log.e("SaveTransferActivity", error.getClass().getName() + ": " + error.getMessage(), error);
    }
    static void emit(JSONObject event) { events.add(event.toString()); }
    static void message(String title, String text) {
        try { emit(new JSONObject().put("kind", "message").put("title", title).put("text", text)); }
        catch (Exception error) { logged(error); }
    }
    public static String managementPoll() { String event = events.poll(); return event == null ? "" : event; }
    public static boolean openSaveTransfer() { return managementAction("open", "{}"); }
    public static boolean managementAction(String action, String argument) {
        if (busy) return false;
        busy = true;
        worker.execute(() -> {
            try { perform(action, new JSONObject(argument)); }
            catch (Exception error) {
                logged(error);
                message("Save transfer", action.equals("export") ? "Unable to prepare export. Your save has not changed." :
                    action.equals("import") ? "Unable to prepare import. Your save has not changed. " + error.getMessage() :
                    "Unable to finish save management. Your save has not changed. " + error.getMessage());
            }
            finally { busy = false; }
        });
        return true;
    }
    private static void choices(String action) throws Exception {
        Context c = SaveSlots.activity(); JSONArray rows = new JSONArray(); String title;
        if (action.equals("open")) {
            title = "Manage saves";
            rows.put(new JSONObject().put("label", "Export save").put("action", "exports"));
            rows.put(new JSONObject().put("label", "Import save").put("action", "pick"));
            rows.put(new JSONObject().put("label", "Rename save").put("action", "renames"));
            rows.put(new JSONObject().put("label", "Delete save").put("action", "deletes"));
        } else {
            title = action.equals("exports") ? "Export save" : action.equals("renames") ? "Rename save" : action.equals("destinations") ? "Import " + imported.name : "Delete save";
            JSONArray profiles = action.equals("deletes") ? SaveSlots.deleteChoices(c) : action.equals("destinations") ? importChoices(c, imported.name) : exportChoices(c);
            for (int i = 0; i < profiles.length(); i++) {
                JSONObject row = profiles.getJSONObject(i);
                row.put("action", action.equals("exports") ? "export" : action.equals("renames") ? "renameInput" : action.equals("destinations") ? "importChoice" : "deleteChoice"); rows.put(row);
            }
        }
        emit(new JSONObject().put("kind", "list").put("title", title).put("rows", rows));
    }
    private static void perform(String action, JSONObject row) throws Exception {
        Activity a = SaveSlots.activity();
        if (action.equals("open")) { finishInstalled(a); choices(action); }
        else if (action.equals("exports") || action.equals("renames") || action.equals("deletes") || action.equals("destinations")) choices(action);
        else if (action.equals("pick")) a.runOnUiThread(() -> a.startActivity(new Intent(a, SaveTransferActivity.class)));
        else if (action.equals("export")) {
            int id = row.getInt("id"); String name = SaveSlots.profileName(a, id);
            // The game popup blocks player input. The worker takes RulesLock through capture(),
            // including the matching preference flush, so no game write can cross this snapshot.
            byte[][] payload = snapshot(a, id, id == SaveSlots.active() ? SaveSlots.capture() : null);
            ensureStage(a); File file = new File(stage(a), "export.zip");
            try {
                writeArchive(file, payload, name);
                try { publish(a, file, name); }
                catch (Exception error) { logged(error); message("Save transfer", "Unable to write export. Your save has not changed."); }
            }
            finally { if (file.exists() && !file.delete()) throw new IOException("Unable to remove export staging"); }
        } else if (action.equals("renameInput")) {
            emit(new JSONObject().put("kind", "rename").put("id", row.getInt("id")).put("label", SaveSlots.profileName(a, row.getInt("id"))));
        } else if (action.equals("rename")) {
            SaveSlots.rename(a, row.getInt("id"), row.getString("name"));
            Log.i("SaveTransferActivity", "SAVE_RENAMED slot=" + row.getInt("id"));
            message("Save renamed", "Renamed to " + SaveSlots.profileName(a, row.getInt("id")));
        } else if (action.equals("deleteChoice") || action.equals("importChoice")) {
            if (action.equals("importChoice") && row.getBoolean("create")) { perform("import", row); return; }
            String name = SaveSlots.profileName(a, row.getInt("id"));
            row.put("action", action.equals("deleteChoice") ? "delete" : "import").put("confirmed", true);
            emit(new JSONObject().put("kind", "confirm").put("title", (action.equals("deleteChoice") ? "Delete " : "Replace ") + name + "?")
                .put("text", action.equals("deleteChoice") ? "Permanently delete " + name + " and its client data?" : "Replace " + name + " with " + imported.name + "? A recovery copy will be kept.").put("row", row));
        } else if (action.equals("delete")) {
            SaveSlots.prepareDelete(a, row.getInt("id"), row.getBoolean("confirmed"));
            Log.i("SaveTransferActivity", "SAVE_DELETE_PREPARED slot=" + row.getInt("id"));
            SaveSlots.restart(a, SaveSlots.active(), false, false, true);
        } else if (action.equals("import")) {
            if (imported == null || !SaveSlots.recognize(imported.payload[0])) throw new IOException("Campaign is not readable by the native engine");
            int id = row.getInt("id"); boolean create = row.getBoolean("create");
            prepare(a, imported.payload, id, create, row.optBoolean("confirmed", false), imported.name);
            Log.i("SaveTransferActivity", "SAVE_IMPORT_PREPARED slot=" + id + " create=" + create);
            SaveSlots.restart(a, id, create, true);
        } else if (action.equals("cancel")) { imported = null; clearPrepared(a); Log.i("SaveTransferActivity", "SAVE_MANAGEMENT_CANCELLED"); }
        else throw new IOException("Unknown save action");
    }
    private static void publish(Context c, File file, String name) throws Exception {
        String requested = filename(name, new Date());
        if (Build.VERSION.SDK_INT >= 29) {
            Uri uri = null;
            try {
                ContentValues values = new ContentValues(); values.put(MediaStore.MediaColumns.DISPLAY_NAME, requested);
                values.put(MediaStore.MediaColumns.MIME_TYPE, "application/zip");
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/Exvius Saves/"); values.put(MediaStore.MediaColumns.IS_PENDING, 1);
                uri = c.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) throw new IOException("Unable to create export");
                try (OutputStream out = c.getContentResolver().openOutputStream(uri, "w")) { copy(file, out); }
                values.clear(); values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                if (c.getContentResolver().update(uri, values, null, null) != 1) throw new IOException("Unable to publish export");
                String actual;
                try (android.database.Cursor cursor = c.getContentResolver().query(uri, new String[]{MediaStore.MediaColumns.DISPLAY_NAME}, null, null, null)) {
                    if (cursor == null || !cursor.moveToFirst()) throw new IOException("Unable to read the exported filename");
                    actual = cursor.getString(0);
                }
                Log.i("SaveTransferActivity", "SAVE_EXPORTED slot=" + name + " file=" + actual);
                message("Save exported", "Exported to Download/Exvius Saves/" + actual);
            } catch (Exception error) {
                logged(error);
                if (uri != null) try { c.getContentResolver().delete(uri, null, null); } catch (RuntimeException cleanup) { logged(cleanup); }
                throw error;
            }
        } else {
            if (c.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED)
                throw new IOException("Download access is unavailable");
            File directory = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Exvius Saves");
            if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Unable to create export folder");
            File result = new File(directory, requested); int n = 1;
            while (!result.createNewFile()) result = new File(directory, requested.substring(0, requested.length()-4) + "-" + n++ + ".zip");
            try (FileOutputStream out = new FileOutputStream(result)) { copy(file, out); out.getFD().sync(); }
            catch (Exception error) { logged(error); result.delete(); throw error; }
            message("Save exported", "Exported to Download/Exvius Saves/" + result.getName());
        }
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (state == null) {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/zip").addCategory(Intent.CATEGORY_OPENABLE);
            if (Build.VERSION.SDK_INT >= 26) intent.putExtra("android.provider.extra.INITIAL_URI", Uri.parse("content://com.android.externalstorage.documents/document/primary%3ADownload%2FExvius%20Saves"));
            try { startActivityForResult(intent, PICK_IMPORT); }
            catch (RuntimeException error) { logged(error); message("Save transfer", "Unable to open import picker"); finish(); }
        }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_IMPORT) return;
        if (result != RESULT_OK || data == null || data.getData() == null) { finish(); managementAction("open", "{}"); return; }
        Uri uri = data.getData(); busy = true;
        worker.execute(() -> {
            try {
                ensureStage(this); File archive = new File(stage(this), "import.zip");
                try (InputStream in = getContentResolver().openInputStream(uri)) {
                    if (in == null) throw new IOException("Unable to open import");
                    SaveSlots.atomic(archive, SaveSlots.read(in, 128 * 1024 * 1024));
                }
                imported = readNamedArchive(archive); choices("destinations");
            } catch (Exception error) { logged(error); message("Save transfer", "Unable to transfer save: " + error.getMessage()); }
            finally { busy = false; runOnUiThread(this::finish); }
        });
    }
    static void copy(File input, OutputStream out) throws IOException {
        if (out == null) throw new IOException("Output document is unavailable");
        try (InputStream in = new FileInputStream(input)) { byte[] buffer = new byte[65536]; int n; while ((n=in.read(buffer)) != -1) out.write(buffer,0,n); }
    }
    static byte[][] snapshot(Context c, int id, byte[][] activeSnapshot) throws Exception {
        if (!SaveSlots.allocated(SaveSlots.catalogue(c), id)) throw new IOException("Profile is unavailable");
        if (id == SaveSlots.active()) {
            if (activeSnapshot == null) throw new IOException("Return to the game and reopen save transfer");
            return activeSnapshot;
        }
        File[] files = targets(c, id); byte[][] payload = new byte[files.length][];
        for (int i = 0; i < files.length; i++) payload[i] = SaveSlots.bytes(files[i]);
        return payload;
    }
    static JSONArray exportChoices(Context c) throws Exception { return SaveSlots.profileChoices(c).getJSONArray("profiles"); }
    static JSONArray importChoices(Context c, String name) throws Exception {
        JSONObject choices = SaveSlots.profileChoices(c); JSONArray profiles = choices.getJSONArray("profiles"), rows = new JSONArray();
        if (choices.getInt("free") != 0) rows.put(new JSONObject().put("id", choices.getInt("free")).put("label", "New profile: " + name).put("create", true));
        for (int i = 0; i < profiles.length(); i++) {
            JSONObject profile = profiles.getJSONObject(i);
            rows.put(new JSONObject().put("id", profile.getInt("id")).put("label", profile.getString("label")).put("create", false));
        }
        return rows;
    }
    static String filename(String name, Date when) {
        String safe = SaveSlots.cleanName(name).replaceAll("[\\\\/:*?\"<>|]", "_").replaceAll("[. ]+$", "");
        if (safe.isEmpty()) safe = "New save";
        return safe + "-" + new SimpleDateFormat("yyyy-MM-dd_HHmmssZ", Locale.ROOT).format(when) + ".zip";
    }
    static String hash(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes); StringBuilder result = new StringBuilder();
        for (byte b : digest) result.append(String.format(Locale.ROOT, "%02x", b & 255)); return result.toString();
    }
    static void campaign(byte[] bytes) throws Exception {
        if (bytes == null) throw new IOException("Missing campaign");
        JSONObject root = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
        if (!(root.get("version") instanceof Number)) throw new IOException("Unrecognized campaign version");
        for (String key : new String[]{"meta","identity","rank","currencies","inventory","party","progress"}) root.getJSONObject(key);
        root.getJSONArray("roster");
    }
    static Document preferences(byte[] bytes) throws Exception {
        // Android's parser implementations do not all expose the desktop Xerces feature names.
        // The native preference format is UTF-8. Reject DTD declarations before parsing and
        // keep an entity resolver as a second boundary without depending on optional features.
        String source=StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
            .decode(java.nio.ByteBuffer.wrap(bytes)).toString();
        String upper=source.toUpperCase(Locale.ROOT);
        if(source.indexOf('\0')>=0 || upper.contains("<!DOCTYPE") || upper.contains("<!ENTITY")) throw new IOException("Unsupported preference declaration");
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        // XInclude is disabled by default. Android throws even when explicitly setting false.
        factory.setExpandEntityReferences(false);
        javax.xml.parsers.DocumentBuilder builder=factory.newDocumentBuilder();
        builder.setEntityResolver((publicId,systemId) -> { throw new org.xml.sax.SAXException("External preference entity"); });
        Document document = builder.parse(new ByteArrayInputStream(bytes));
        String encoding=document.getXmlEncoding();
        if(encoding!=null&&!encoding.equalsIgnoreCase("UTF-8")&&!encoding.equalsIgnoreCase("UTF8")) throw new IOException("Unsupported preference encoding");
        if (!document.getDocumentElement().getTagName().equals("map")) throw new IOException("Invalid preference map");
        Set<String> keys = new HashSet<>(); NodeList rows = document.getDocumentElement().getChildNodes();
        for (int i=0;i<rows.getLength();i++) {
            Node node=rows.item(i); if (!(node instanceof Element)) { if (node.getNodeType()==Node.TEXT_NODE && !node.getTextContent().trim().isEmpty()) throw new IOException("Invalid preference text"); continue; }
            Element row=(Element)node; String type=row.getTagName();
            if (!row.hasAttribute("name") || !keys.add(row.getAttribute("name"))) throw new IOException("Invalid preference key");
            String value=row.getAttribute("value");
            if(!type.equals("set")) for(Node child=row.getFirstChild();child!=null;child=child.getNextSibling())
                if(child instanceof Element) throw new IOException("Invalid nested preference value");
            switch(type) {
                case "string": for(Node child=row.getFirstChild();child!=null;child=child.getNextSibling()) if(child instanceof Element) throw new IOException("Invalid string preference"); break;
                case "int": Integer.parseInt(value); break;
                case "long": Long.parseLong(value); break;
                case "float": Float.parseFloat(value); break;
                case "boolean": if(!value.equals("true")&&!value.equals("false")) throw new IOException("Invalid boolean preference"); break;
                case "set": for(Node child=row.getFirstChild();child!=null;child=child.getNextSibling()) if(child instanceof Element) {
                    if(!((Element)child).getTagName().equals("string")) throw new IOException("Invalid preference set");
                    for(Node text=child.getFirstChild();text!=null;text=text.getNextSibling()) if(text instanceof Element) throw new IOException("Invalid preference set value");
                } break;
                default: throw new IOException("Unknown preference type");
            }
        }
        return document;
    }
    static byte[] xml(Document document) throws Exception {
        Transformer transformer = TransformerFactory.newInstance().newTransformer();
        transformer.setOutputProperty(OutputKeys.ENCODING,"UTF-8"); ByteArrayOutputStream out=new ByteArrayOutputStream();
        transformer.transform(new DOMSource(document),new StreamResult(out)); return out.toByteArray();
    }
    static byte[] gamePreferences(byte[] player, byte[] shared) throws Exception {
        Document result=preferences(player == null ? "<map/>".getBytes(StandardCharsets.UTF_8) : player);
        Element root=result.getDocumentElement();
        for(Node row=root.getFirstChild();row!=null;) { Node next=row.getNextSibling(); if(row instanceof Element && ((Element)row).getAttribute("name").startsWith("keyF_")) root.removeChild(row); row=next; }
        if(shared!=null) { Document original=preferences(shared);
            for(Node row=original.getDocumentElement().getFirstChild();row!=null;row=row.getNextSibling())
                if(row instanceof Element && ((Element)row).getAttribute("name").startsWith("keyF_")) root.appendChild(result.importNode(row,true));
        }
        return xml(result);
    }
    static void validate(byte[][] payload) throws Exception {
        if(payload.length!=ENTRIES.length) throw new IOException("Invalid save payload"); campaign(payload[0]);
        for(int i=1;i<=3;i++) if(payload[i]!=null) preferences(payload[i]);
    }
    static void writeArchive(File file, byte[][] snapshot, String label) throws Exception {
        validate(snapshot); byte[][] payload=snapshot.clone();
        if(payload[1]!=null) payload[1]=gamePreferences(payload[1],null);
        JSONObject manifest=new JSONObject().put("game","exvius.offline").put("format","exvius-save-1")
            .put("source_slot",label).put("profile_name",SaveSlots.cleanName(label)).put("exported_at",new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ",Locale.ROOT).format(new Date()));
        JSONObject entries=new JSONObject();
        for(int i=0;i<payload.length;i++) entries.put(ENTRIES[i],payload[i]==null ? JSONObject.NULL : new JSONObject().put("length",payload[i].length).put("sha256",hash(payload[i])));
        manifest.put("entries",entries);
        try(FileOutputStream raw=new FileOutputStream(file); ZipOutputStream zip=new ZipOutputStream(raw)) {
            zip.putNextEntry(new ZipEntry("manifest.json")); zip.write(manifest.toString().getBytes(StandardCharsets.UTF_8)); zip.closeEntry();
            for(int i=0;i<payload.length;i++) if(payload[i]!=null) { zip.putNextEntry(new ZipEntry(ENTRIES[i]));zip.write(payload[i]);zip.closeEntry(); }
            zip.finish(); raw.getFD().sync();
        }
    }
    static final class Archive {
        final byte[][] payload; final String name;
        Archive(byte[][] payload, String name) { this.payload = payload; this.name = name; }
    }
    static byte[][] readArchive(File file) throws Exception { return readNamedArchive(file).payload; }
    static Archive readNamedArchive(File file) throws Exception {
        byte[][] payload=new byte[ENTRIES.length][]; JSONObject manifest=null; Set<String> seen=new HashSet<>();
        try(ZipFile zip=new ZipFile(file)) {
            Enumeration<? extends ZipEntry> entries=zip.entries(); long total=0;
            while(entries.hasMoreElements()) {
                ZipEntry entry=entries.nextElement(); String name=entry.getName();
                int index=Arrays.asList(ENTRIES).indexOf(name);
                if(entry.isDirectory() || (!name.equals("manifest.json") && index<0) || !seen.add(name)) throw new IOException("Unsupported or duplicate ZIP entry");
                int limit=index<0?65536:ENTRY_LIMIT;
                if(entry.getSize()<0 || entry.getSize()>limit || (total+=entry.getSize())>128*1024*1024L) throw new IOException("Invalid ZIP entry length");
                byte[] bytes; try(InputStream in=zip.getInputStream(entry)) { bytes=SaveSlots.read(in,limit); }
                CRC32 crc=new CRC32();crc.update(bytes);
                if(bytes.length!=entry.getSize() || crc.getValue()!=entry.getCrc()) throw new IOException("Damaged ZIP entry");
                if(index<0) manifest=new JSONObject(new String(bytes,StandardCharsets.UTF_8)); else payload[index]=bytes;
            }
        }
        if(manifest==null || !manifest.getString("game").equals("exvius.offline") || !manifest.getString("format").equals("exvius-save-1")) throw new IOException("Unrecognized save archive");
        JSONObject hashes=manifest.optJSONObject("entries");
        if(hashes!=null) for(int i=0;i<ENTRIES.length;i++) {
            if(!hashes.has(ENTRIES[i])) continue;
            if(hashes.isNull(ENTRIES[i])) { if(payload[i]!=null) throw new IOException("Unexpected optional store"); continue; }
            JSONObject entry=hashes.getJSONObject(ENTRIES[i]);
            if(payload[i]==null || (entry.has("length") && entry.getLong("length")!=payload[i].length) || (entry.has("sha256") && !hash(payload[i]).equals(entry.getString("sha256")))) throw new IOException("Save integrity check failed");
        }
        validate(payload); if(payload[1]!=null) payload[1]=gamePreferences(payload[1],null);
        String name = manifest.has("profile_name") ? SaveSlots.cleanName(manifest.getString("profile_name")) : "";
        return new Archive(payload, name.isEmpty() ? SaveSlots.playerName(payload[0]) : name);
    }

    static File stage(Context c) { return new File(SaveSlots.state(c),"slots/import"); }
    static File journal(Context c) { return new File(stage(c),"journal.json"); }
    static void ensureStage(Context c) throws IOException {
        if(!stage(c).isDirectory()&&!stage(c).mkdirs()) throw new IOException("Unable to create import staging");
    }
    static File[] targets(Context c,int id) {
        return new File[]{SaveSlots.campaign(c,id),new File(SaveSlots.prefs(c),SaveSlots.storeName("gamedata",id)+".xml"),
            new File(SaveSlots.prefs(c),SaveSlots.storeName("Cocos2dxPrefsFile",id)+".xml"),new File(SaveSlots.prefs(c),SaveSlots.storeName("auth",id)+".xml"),SaveSlots.keychain(c,id)};
    }
    static JSONObject readJournal(Context c) throws Exception { return new JSONObject(new String(SaveSlots.bytes(journal(c)),StandardCharsets.UTF_8)); }
    static void marker(Context c,JSONObject value) throws Exception { SaveSlots.atomic(journal(c),value.toString().getBytes(StandardCharsets.UTF_8)); }
    static void prepare(Context c,byte[][] payload,int id,boolean create,boolean confirmed) throws Exception {
        prepare(c, payload, id, create, confirmed, SaveSlots.playerName(payload[0]));
    }
    static void prepare(Context c,byte[][] payload,int id,boolean create,boolean confirmed,String name) throws Exception {
        validate(payload); JSONObject catalogue=SaveSlots.catalogue(c);
        if(create ? id!=SaveSlots.unused(catalogue) : !confirmed || !SaveSlots.allocated(catalogue,id)) throw new IOException("Destination was not confirmed");
        if(journal(c).exists()) throw new IOException("An import is already pending");
        ensureStage(c); JSONObject hashes=new JSONObject();
        for(int i=0;i<payload.length;i++) {
            File target=new File(stage(c),"prepared/"+i);
            if(payload[i]!=null) SaveSlots.atomic(target,payload[i]); else if(target.exists()&&!target.delete()) throw new IOException("Unable to clear staged store");
            hashes.put(ENTRIES[i],payload[i]==null?JSONObject.NULL:hash(payload[i]));
        }
        JSONObject next=new JSONObject(catalogue.toString());
        if(create) next.getJSONArray("slots").put(new JSONObject().put("id",id).put("label",""));
        SaveSlots.row(next, id).put("label", SaveSlots.cleanName(name)).put("renamed", true).put("awaiting_name", false);
        next.put("active",id); SaveSlots.validateCatalogue(next);
        marker(c,new JSONObject().put("state","prepared").put("slot",id).put("create",create).put("confirmed",confirmed)
            .put("hashes",hashes).put("catalogue",next).put("backup","save-import-"+UUID.randomUUID().toString()));
    }
    static void checkpoint(int point) throws IOException { /* JVM failure injection overrides this method in test copies only. */ }
    static synchronized void install(Context c) throws Exception {
        JSONObject transaction=readJournal(c);
        if(transaction.getString("state").equals("installed")) return;
        int id=transaction.getInt("slot"); boolean create=transaction.getBoolean("create");
        if(id<1||id>SaveSlots.LIMIT || (!create&&!transaction.getBoolean("confirmed"))) throw new IOException("Invalid import destination");
        byte[][] payload=new byte[ENTRIES.length][]; JSONObject hashes=transaction.getJSONObject("hashes");
        for(int i=0;i<payload.length;i++) {
            payload[i]=SaveSlots.bytes(new File(stage(c),"prepared/"+i));
            if(hashes.isNull(ENTRIES[i]) ? payload[i]!=null : payload[i]==null || !hash(payload[i]).equals(hashes.getString(ENTRIES[i]))) throw new IOException("Incomplete staged save");
        }
        validate(payload); SaveSlots.validateCatalogue(transaction.getJSONObject("catalogue"));
        File[] destinations=targets(c,id);
        if(!transaction.optBoolean("backed_up",false)) {
            if(!create) {
                File backup=new File(SaveSlots.state(c),"backups/"+transaction.getString("backup"));
                JSONObject present=new JSONObject(), paths=new JSONObject();
                String privateRoot=new File(c.getApplicationInfo().dataDir).getCanonicalPath()+File.separator;
                for(int i=0;i<destinations.length;i++) {
                    String destination=destinations[i].getCanonicalPath();
                    if(!destination.startsWith(privateRoot)) throw new IOException("Recovery destination is outside game data");
                    paths.put(ENTRIES[i],new JSONObject().put("stored_file",Integer.toString(i)).put("relative_path",destination.substring(privateRoot.length())));
                    byte[] old=SaveSlots.bytes(destinations[i]);present.put(ENTRIES[i],old!=null);
                    if(old!=null) SaveSlots.atomic(new File(backup,Integer.toString(i)),old);
                }
                present.put("destination_slot",id).put("paths",paths);
                SaveSlots.atomic(new File(backup,"present.json"),present.toString().getBytes(StandardCharsets.UTF_8));
            }
            transaction.put("backed_up",true);marker(c,transaction);
        }
        checkpoint(0);
        // Only slot 1 owns the original shared resource-version entries. Merge from disk after the writer stopped.
        if(id==1) payload[1]=gamePreferences(payload[1],SaveSlots.bytes(destinations[1]));
        for(int i=0;i<payload.length;i++) {
            if(payload[i]!=null) SaveSlots.atomic(destinations[i],payload[i]);
            else if(destinations[i].exists()&&!destinations[i].delete()) throw new IOException("Unable to clear replaced store");
            File stale=new File(destinations[i]+".bak");if(stale.exists()&&!stale.delete()) throw new IOException("Unable to clear replaced preference backup");
            checkpoint(i+1);
        }
        SaveSlots.storeCatalogue(c,transaction.getJSONObject("catalogue"));checkpoint(6);
        transaction.put("state","installed");marker(c,transaction);
    }
    static synchronized void recover(Context c) throws Exception {
        File file=journal(c);
        if(new File(file+".bak").exists()) try(InputStream ignored=new android.util.AtomicFile(file).openRead()) {}
        if(file.exists()&&!readJournal(c).getString("state").equals("installed")) install(c);
    }
    static void clearPrepared(Context c) throws Exception {
        if(journal(c).exists()) return;
        removeTree(new File(stage(c),"prepared"));new File(stage(c),"import.zip").delete();
    }
    static void finishInstalled(Context c) throws Exception {
        if(!journal(c).exists()||!readJournal(c).getString("state").equals("installed")) return;
        removeTree(new File(stage(c),"prepared"));
        new File(stage(c),"import.zip").delete();
        if(!journal(c).delete()) throw new IOException("Unable to finish import recovery");
    }
    private static void removeTree(File directory) throws IOException {
        if(!directory.exists()) return;
        File[] files=directory.listFiles();if(files==null) throw new IOException("Unable to inspect import staging");
        for(File file:files) { if(file.isDirectory()) removeTree(file);else if(!file.delete()) throw new IOException("Unable to clean import staging"); }
        if(!directory.delete()) throw new IOException("Unable to clean import staging");
    }
}
