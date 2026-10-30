package com.exvius.local;

import android.system.ErrnoException;
import android.system.Os;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Installs static game files without touching saves or application code. */
public final class DataPack {
    private DataPack() {}

    public static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[262144];
        try (InputStream input = new FileInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        StringBuilder result = new StringBuilder(64);
        for (byte value : digest.digest()) result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    public static File destination(File files, String name) throws IOException {
        if (name.indexOf('\\') >= 0 || name.startsWith("/") || name.contains("../"))
            throw new IOException("Invalid data pack path");
        String relative;
        if (name.startsWith("static/")) {
            relative = "exvius/data/" + name;
        } else if (name.startsWith("native/")) {
            relative = name.substring(7);
            if (!relative.matches("(?:mst|localized_texts|common_lang|en|homeMarquee)/.+"))
                throw new IOException("Unsupported game data path");
        } else if (name.equals("metadata/registry.json")) {
            relative = "exvius/data/registry.json";
        } else {
            throw new IOException("Unsupported data pack entry");
        }
        File root = files.getCanonicalFile(), target = new File(root, relative).getCanonicalFile();
        if (!target.getPath().startsWith(root.getPath() + File.separator))
            throw new IOException("Data pack path escapes game storage");
        return target;
    }

    public static void extract(File archive, File files, long expectedBytes) throws IOException {
        try (ZipFile zip = new ZipFile(archive)) {
            if (zip.size() > 100000) throw new IOException("Data pack has too many entries");
            Set<String> names = new HashSet<>();
            long declared = 0;
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                destination(files, entry.getName());
                if (!names.add(entry.getName()) || entry.getSize() < 0)
                    throw new IOException("Invalid data pack directory");
                declared = Math.addExact(declared, entry.getSize());
            }
            if (declared != expectedBytes) throw new IOException("Data pack size does not match");
            entries = zip.entries();
            byte[] buffer = new byte[262144];
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                File target = destination(files, entry.getName()), parent = target.getParentFile();
                if (!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Cannot create game folder");
                File partial = new File(parent, target.getName() + ".installing");
                long written = 0;
                try {
                    try (InputStream input = zip.getInputStream(entry);
                         FileOutputStream output = new FileOutputStream(partial)) {
                        int count;
                        while ((count = input.read(buffer)) != -1) {
                            written += count;
                            if (written > entry.getSize()) throw new IOException("Invalid expanded file size");
                            output.write(buffer, 0, count);
                        }
                    }
                    if (written != entry.getSize()) throw new IOException("Incomplete game file");
                    try {
                        Os.rename(partial.getPath(), target.getPath());
                    } catch (ErrnoException error) {
                        throw new IOException("Cannot finish installing game file", error);
                    }
                } finally {
                    if (partial.exists()) partial.delete();
                }
            }
        }
    }
}
