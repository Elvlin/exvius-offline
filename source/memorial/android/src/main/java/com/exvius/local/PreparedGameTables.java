package com.exvius.local;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Version-bound prepared table data, with the original decoder as fallback. */
public final class PreparedGameTables {
    private PreparedGameTables() {}

    private static String hex(byte[] bytes) {
        char[] result = new char[bytes.length * 2];
        char[] digits = "0123456789abcdef".toCharArray();
        for (int i = 0; i < bytes.length; i++) {
            result[i * 2] = digits[(bytes[i] & 255) >>> 4];
            result[i * 2 + 1] = digits[bytes[i] & 15];
        }
        return new String(result);
    }

    public static String readPrepared(String path, String password, String iv) {
        File file = new File(path), parent = file.getParentFile();
        while (parent != null && !parent.getName().equals("mst")
                && !parent.getName().equals("localized_texts")) parent = parent.getParentFile();
        if (parent == null || parent.getParentFile() == null) return null;
        File directory = new File(parent.getParentFile(), "exvius/data/static/prepared_tables");
        if (!directory.isDirectory()) return null;
        boolean timing = new File(directory, "timing.enabled").isFile();
        long started = timing ? System.nanoTime() : 0;
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[262144];
            long size = 0;
            try (FileInputStream input = new FileInputStream(file)) {
                int count;
                while ((count = input.read(buffer)) != -1) {
                    digest.update(buffer, 0, count);
                    size += count;
                }
            }
            String encryptedHash = hex(digest.digest());
            String parameterHash = hex(digest.digest((password + "\0" + iv).getBytes(StandardCharsets.UTF_8)));
            File prepared = new File(directory, file.getName() + "." + size + "."
                + encryptedHash + "." + parameterHash + ".utf8");
            if (!prepared.isFile()) return null;
            long verified = timing ? System.nanoTime() : 0;
            long length = prepared.length();
            if (length > Integer.MAX_VALUE - 8) return null;
            byte[] bytes = new byte[(int) length];
            try (FileInputStream input = new FileInputStream(prepared)) {
                int offset = 0, count;
                while (offset < bytes.length && (count = input.read(bytes, offset, bytes.length - offset)) != -1)
                    offset += count;
                if (offset != bytes.length || input.read() != -1) throw new IOException("Prepared table changed");
            }
            long read = timing ? System.nanoTime() : 0;
            String result = new String(bytes, StandardCharsets.UTF_8);
            if (timing) android.util.Log.i("ExviusTables", "TABLE_PREPARED path=" + path
                + " bytes=" + length + " verify_ns=" + (verified - started)
                + " read_ns=" + (read - verified) + " string_ns=" + (System.nanoTime() - read)
                + " total_ns=" + (System.nanoTime() - started));
            return result;
        } catch (Exception unavailable) {
            if (timing) android.util.Log.i("ExviusTables", "TABLE_PREPARED_UNAVAILABLE path=" + path);
            return null;
        }
    }

    public static String decodeGameTable(String path, String password, String iv) throws Exception {
        String prepared = readPrepared(path, password, iv);
        if (prepared != null) return prepared;
        android.util.Log.i("ExviusTables", "TABLE_FALLBACK path=" + path);
        return decodeEncrypted(path, password, iv);
    }

    private static String decodeEncrypted(String path, String password, String iv) throws Exception {
        byte[] key = new byte[16];
        byte[] supplied = password.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        System.arraycopy(supplied, 0, key, 0, Math.min(key.length, supplied.length));
        javax.crypto.Cipher cipher = javax.crypto.Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(javax.crypto.Cipher.DECRYPT_MODE,
            new javax.crypto.spec.SecretKeySpec(key, "AES"),
            new javax.crypto.spec.IvParameterSpec(iv.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        File file = new File(path);
        StringBuilder result = new StringBuilder((int) Math.min(file.length(), Integer.MAX_VALUE - 8));
        try (java.io.BufferedReader input = new java.io.BufferedReader(new java.io.FileReader(file), 65536)) {
            String line;
            boolean first = true;
            while ((line = input.readLine()) != null) {
                byte[] plain = cipher.doFinal(android.util.Base64.decode(line, android.util.Base64.DEFAULT));
                // GL9 stores a second PKCS padding layer inside the CBC payload.
                // Match LapisJNI::unpaddingWithPKCSX, including its invalid marker.
                int padding = plain[plain.length - 1];
                if (padding > 0 && padding != 16 - (plain.length - padding) % 16) plain = new byte[1];
                else plain = java.util.Arrays.copyOf(plain, plain.length - padding);
                if (!first) result.append('\n');
                result.append(new String(plain, java.nio.charset.StandardCharsets.UTF_8));
                first = false;
            }
        }
        return result.toString();
    }
}
