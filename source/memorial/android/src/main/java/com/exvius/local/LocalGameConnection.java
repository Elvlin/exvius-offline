package com.exvius.local;

import android.text.TextUtils;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FilterInputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Adapts the client's existing connection API to an in-process game call. */
final class LocalGameConnection extends HttpURLConnection {
    private final ByteArrayOutputStream outgoing = new ByteArrayOutputStream();
    private LocalGameBridge.Response response;
    private Map<String, List<String>> responseHeaders;
    private IOException failure;
    private File localFile;
    private long fileStart;
    private long fileLength;

    LocalGameConnection(URL address) { super(address); }

    @Override public void connect() {
        // The Cocos client may connect before writing its request body.
        // Dispatch only when it asks for a response, after the body is ready.
    }

    private synchronized void dispatch() throws IOException {
        if (failure != null) throw failure;
        if (response != null) return;
        Map<String, String> headers = new LinkedHashMap<>();
        for (Map.Entry<String, List<String>> entry : getRequestProperties().entrySet()) {
            headers.put(entry.getKey(), TextUtils.join(", ", entry.getValue()));
        }
        try {
            if ("GET".equals(getRequestMethod()) || "HEAD".equals(getRequestMethod()))
                localFile = LocalGameBridge.localFile(url.getPath());
            if (localFile != null) {
                fileLength = localFile.length();
                long total = fileLength;
                int status = 200;
                Map<String, String> fields = new LinkedHashMap<>();
                fields.put("Accept-Ranges", "bytes");
                String mime = guessContentTypeFromName(localFile.getName());
                fields.put("Content-Type", mime == null ? "application/octet-stream" : mime);
                String range = null;
                for (Map.Entry<String, String> entry : headers.entrySet())
                    if ("Range".equalsIgnoreCase(entry.getKey())) range = entry.getValue();
                if (range != null) {
                    try {
                        if (!range.matches("bytes=\\d*-\\d*")) throw new IllegalArgumentException();
                        String[] bounds = range.substring(6).split("-", -1);
                        long end = total - 1;
                        if (bounds[0].isEmpty()) fileStart = Math.max(0, total - Long.parseLong(bounds[1]));
                        else {
                            fileStart = Long.parseLong(bounds[0]);
                            if (!bounds[1].isEmpty()) end = Math.min(end, Long.parseLong(bounds[1]));
                        }
                        if (fileStart >= total || end < fileStart) throw new IllegalArgumentException();
                        fileLength = end - fileStart + 1;
                        fields.put("Content-Range", "bytes " + fileStart + "-" + end + "/" + total);
                        status = 206;
                    } catch (IllegalArgumentException error) {
                        fields.put("Content-Range", "bytes */" + total);
                        fileLength = 0;
                        status = 416;
                    }
                }
                fields.put("Content-Length", Long.toString(fileLength));
                response = new LocalGameBridge.Response(status, fields, new byte[0]);
            } else {
                response = LocalGameBridge.request(getRequestMethod(), url.getFile(),
                                                   outgoing.toByteArray(), headers);
            }
            connected = true;
            responseCode = response.status;
            responseMessage = responseCode == 200 ? "OK" : responseCode == 206 ? "Partial Content" :
                responseCode == 416 ? "Range Not Satisfiable" : "Local game error";
            Map<String, List<String>> fields = new LinkedHashMap<>();
            fields.put(null, Collections.singletonList("HTTP/1.1 " + responseCode + " " + responseMessage));
            for (Map.Entry<String, String> entry : response.headers.entrySet()) {
                fields.put(entry.getKey(), Collections.singletonList(entry.getValue()));
            }
            responseHeaders = Collections.unmodifiableMap(fields);
        } catch (IOException error) {
            failure = error;
            throw error;
        }
    }

    @Override public OutputStream getOutputStream() throws IOException {
        if (response != null) throw new IOException("The local request was already completed");
        return outgoing;
    }
    @Override public InputStream getInputStream() throws IOException {
        dispatch();
        if (responseCode >= 400) throw new IOException("Local game status " + responseCode);
        if ("HEAD".equals(getRequestMethod())) return new ByteArrayInputStream(new byte[0]);
        if (localFile != null) {
            FileInputStream input = new FileInputStream(localFile);
            input.getChannel().position(fileStart);
            return new FilterInputStream(input) {
                private long remaining = fileLength;
                @Override public int read() throws IOException {
                    if (remaining == 0) return -1;
                    int value = super.read();
                    if (value >= 0) remaining--;
                    return value;
                }
                @Override public int read(byte[] bytes, int offset, int length) throws IOException {
                    if (length == 0) return 0;
                    if (remaining == 0) return -1;
                    int count = in.read(bytes, offset, (int) Math.min(length, remaining));
                    if (count > 0) remaining -= count;
                    return count;
                }
                @Override public long skip(long count) throws IOException {
                    long skipped = in.skip(Math.min(Math.max(0, count), remaining));
                    remaining -= skipped;
                    return skipped;
                }
                @Override public int available() throws IOException {
                    return (int) Math.min(in.available(), remaining);
                }
            };
        }
        return new ByteArrayInputStream(response.body);
    }
    @Override public InputStream getErrorStream() {
        try {
            dispatch();
            return responseCode >= 400 ? new ByteArrayInputStream(response.body) : null;
        } catch (IOException error) { return null; }
    }
    @Override public int getResponseCode() throws IOException { dispatch(); return responseCode; }
    @Override public String getResponseMessage() throws IOException { dispatch(); return responseMessage; }
    @Override public Map<String, List<String>> getHeaderFields() {
        try { dispatch(); return responseHeaders; }
        catch (IOException error) { return Collections.emptyMap(); }
    }
    @Override public String getHeaderField(String name) {
        for (Map.Entry<String, List<String>> entry : getHeaderFields().entrySet()) {
            if (name == null ? entry.getKey() == null : name.equalsIgnoreCase(entry.getKey())) {
                return entry.getValue().get(0);
            }
        }
        return null;
    }
    @Override public String getHeaderFieldKey(int index) {
        List<String> keys = new ArrayList<>(getHeaderFields().keySet());
        return index >= 0 && index < keys.size() ? keys.get(index) : null;
    }
    @Override public String getHeaderField(int index) {
        if (index < 0 || index >= getHeaderFields().size()) return null;
        return getHeaderField(getHeaderFieldKey(index));
    }
    @Override public boolean usingProxy() { return false; }
    @Override public void disconnect() { connected = false; }
}
