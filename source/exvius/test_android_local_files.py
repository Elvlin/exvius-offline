"""Run the actual Android file connection on the JVM with framework boundaries stubbed."""
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[2]
JAVA = Path('C:/Program Files/Microsoft/jdk-11.0.12.7-hotspot/bin')


class AndroidLocalFiles(unittest.TestCase):
    def test_cocos_tasks_keep_original_callbacks_for_local_data_files_errors_and_cancel(self):
        with tempfile.TemporaryDirectory(prefix='local-cocos-test-', dir=PROJECT / 'source/build') as work:
            root = Path(work)
            package = root / 'com/exvius/local'
            package.mkdir(parents=True)
            for name, source in {
                'android/text/TextUtils.java': '''package android.text;
public class TextUtils { public static String join(CharSequence s, Iterable<?> values) {
    java.util.StringJoiner out=new java.util.StringJoiner(s);
    for(Object v:values) out.add(v.toString()); return out.toString();
} }''',
                'android/os/Looper.java': '''package android.os;
public class Looper { public static Looper getMainLooper() { return new Looper(); } }''',
                'android/os/Handler.java': '''package android.os;
public class Handler { public Handler(Looper l) {} public boolean post(Runnable r) { r.run(); return true; } }''',
            }.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding='utf-8')
            (package / 'LocalGameBridge.java').write_text('''package com.exvius.local;
import java.io.*; import java.net.*; import java.util.*;
final class LocalGameBridge {
    static File root;
    static java.util.concurrent.CountDownLatch slowStarted=new java.util.concurrent.CountDownLatch(1);
    static File localFile(String path) throws IOException {
        File f=new File(root,new File(path).getName()); return f.isFile()?f:null;
    }
    static boolean existingFile(String address,String destination) throws IOException {
        File f=localFile(new URL(address).getPath());
        return f!=null && f.length()>0 && f.getCanonicalFile().equals(new File(destination).getCanonicalFile());
    }
    static HttpURLConnection openConnection(String address) throws IOException {
        URL url=new URL(address);
        if(!url.getPath().equals("/slow")) return new LocalGameConnection(url);
        return new HttpURLConnection(url) {
            public void connect() {} public void disconnect() {} public boolean usingProxy() { return false; }
            public int getResponseCode() { return 200; } public long getContentLengthLong() { return -1; }
            public InputStream getInputStream() { return new InputStream() {
                public int read() throws IOException { throw new IOException("Use buffered read"); }
                public int read(byte[] b,int offset,int length) throws IOException {
                    slowStarted.countDown();
                    try { Thread.sleep(10000); } catch(InterruptedException e) { throw new IOException("Cancelled"); }
                    return -1;
                }
            }; }
        };
    }
    static Response request(String method,String path,byte[] body,Map<String,String> headers) throws IOException {
        throw new IOException("Local resource missing");
    }
    static final class Response {
        final int status; final Map<String,String> headers; final byte[] body;
        Response(int s,Map<String,String> h,byte[] b) { status=s;headers=h;body=b; }
    }
}''', encoding='utf-8')
            production = PROJECT / 'source/memorial/android/src/main/java/com/exvius/local'
            for name in ['LocalGameConnection.java', 'LocalCocosTasks.java']:
                (package / name).write_bytes((production / name).read_bytes())
            (package / 'CocosSmoke.java').write_text('''package com.exvius.local;
import java.io.*; import java.nio.file.*; import java.security.Permission; import java.util.*;
import java.util.concurrent.*;
public class CocosSmoke {
    private final Queue<Runnable> _taskQueue=new ArrayDeque<>();
    private final CountDownLatch done=new CountDownLatch(1);
    int status=999, starts, finishes, next; long received; byte[] data;
    void onStart(int id) { starts++; }
    void onProgress(int id,long delta,long total,long expected) { received=total; }
    void onFinish(int id,int code,String message,byte[] result) { status=code; data=result; finishes++; }
    void runNextTaskIfExists() { next++; done.countDown(); }
    void await() throws Exception {
        check(done.await(5,TimeUnit.SECONDS),"loading callback timed out");
        check(starts==1 && finishes==1 && next==1,"original callback lifecycle");
    }
    static void check(boolean ok,String message) { if(!ok) throw new AssertionError(message); }
    static CocosSmoke load(String path,String destination) {
        CocosSmoke owner=new CocosSmoke();
        LocalCocosTasks.load(owner,7,"https://offline.invalid/"+path,destination); return owner;
    }
    public static void main(String[] args) throws Exception {
        LocalGameBridge.root=new File(args[0]);
        byte[] bytes=new byte[2097169]; for(int i=0;i<bytes.length;i++) bytes[i]=(byte)i;
        File source=new File(LocalGameBridge.root,"sample.bin"); Files.write(source.toPath(),bytes);
        System.setSecurityManager(new SecurityManager() {
            public void checkPermission(Permission p) {}
            public void checkConnect(String host,int port) { throw new AssertionError("Network attempted"); }
        });
        File target=new File(LocalGameBridge.root,"nested/copied.bin");
        CocosSmoke copy=load("sample.bin",target.getPath()); copy.await();
        check(copy.status==0 && Arrays.equals(Files.readAllBytes(target.toPath()),bytes),"local file copy");
        check(copy.received==bytes.length && copy.data==null,"real file progress");
        long modified=source.lastModified();
        CocosSmoke cached=load("sample.bin",source.getPath()); cached.await();
        check(cached.status==0 && source.lastModified()==modified && source.length()==bytes.length,"cache self-copy protection");
        CocosSmoke memory=load("sample.bin",""); memory.await();
        check(memory.status==0 && Arrays.equals(memory.data,bytes),"local data callback");
        File absent=new File(LocalGameBridge.root,"absent.bin");
        CocosSmoke missing=load("missing.bin",absent.getPath()); missing.await();
        check(missing.status!=0 && !absent.exists(),"missing resource reported success");
        File interrupted=new File(LocalGameBridge.root,"cancelled.bin");
        CocosSmoke cancelled=load("slow",interrupted.getPath());
        check(LocalGameBridge.slowStarted.await(2,TimeUnit.SECONDS),"local cancellation fixture");
        cancelled._taskQueue.add(()->{throw new AssertionError("queued task survived cancellation");});
        LocalCocosTasks.cancel(cancelled); cancelled.await();
        check(cancelled.status!=0 && cancelled._taskQueue.isEmpty() && !interrupted.exists(),"cancelled local file committed");
        try(java.util.stream.Stream<Path> files=Files.walk(LocalGameBridge.root.toPath())) {
            check(files.noneMatch(p->p.getFileName().toString().startsWith(".exvius-load-")),"staging file left behind");
        }
        System.out.println("PASS: original Cocos callback lifecycle, real local progress, file/data reads, cache safety, missing files and cancellation");
    }
}''', encoding='utf-8')
            sources = sorted(str(path) for path in root.rglob('*.java'))
            subprocess.run([str(JAVA / 'javac.exe'), '-d', str(root), *sources], check=True)
            result = subprocess.run([str(JAVA / 'java.exe'), '-cp', str(root),
                                     'com.exvius.local.CocosSmoke', str(root)],
                                    text=True, capture_output=True, check=True)
            self.assertIn('PASS:', result.stdout)
            print(result.stdout.strip())

    def test_actual_connection_streams_files_without_network_or_engine_calls(self):
        with tempfile.TemporaryDirectory(prefix='local-file-test-', dir=PROJECT / 'source/build') as work:
            root = Path(work)
            package = root / 'com/exvius/local'
            package.mkdir(parents=True)
            text = root / 'android/text'
            text.mkdir(parents=True)
            (text / 'TextUtils.java').write_text('''package android.text;
public final class TextUtils {
    public static String join(CharSequence separator, Iterable<?> values) {
        java.util.StringJoiner out = new java.util.StringJoiner(separator);
        for (Object value : values) out.add(value.toString());
        return out.toString();
    }
}
''', encoding='utf-8')
            (package / 'LocalGameBridge.java').write_text('''package com.exvius.local;
import java.io.File;
import java.util.Map;
final class LocalGameBridge {
    static File root;
    static File localFile(String path) throws java.io.IOException { return new File(root, new File(path).getName()); }
    static Response request(String method, String path, byte[] body, Map<String,String> headers) throws java.io.IOException {
        throw new AssertionError("File read escaped to the game engine");
    }
    static final class Response {
        final int status; final Map<String,String> headers; final byte[] body;
        Response(int s, Map<String,String> h, byte[] b) { status=s; headers=h; body=b; }
    }
}
''', encoding='utf-8')
            production = PROJECT / 'source/memorial/android/src/main/java/com/exvius/local/LocalGameConnection.java'
            (package / production.name).write_bytes(production.read_bytes())
            (package / 'FileSmoke.java').write_text('''package com.exvius.local;
import java.io.*;
import java.net.URL;
import java.security.Permission;
import java.util.Arrays;
public final class FileSmoke {
    static void check(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    static LocalGameConnection open(String method, String range) throws Exception {
        LocalGameConnection c = new LocalGameConnection(new URL("https://offline.invalid/sample.bin"));
        c.setRequestMethod(method);
        if (range != null) c.setRequestProperty("Range", range);
        return c;
    }
    public static void main(String[] args) throws Exception {
        LocalGameBridge.root = new File(args[0]);
        byte[] data = new byte[256];
        for (int i=0; i<data.length; i++) data[i]=(byte)i;
        java.nio.file.Files.write(new File(LocalGameBridge.root,"sample.bin").toPath(),data);
        System.setSecurityManager(new SecurityManager() {
            public void checkPermission(Permission p) {}
            public void checkConnect(String host, int port) { throw new AssertionError("Network attempted"); }
        });
        LocalGameConnection full=open("GET",null);
        check(full.getResponseCode()==200,"full status");
        check(full.getContentLengthLong()==256,"full length");
        try(InputStream in=full.getInputStream()) { check(Arrays.equals(in.readAllBytes(),data),"full bytes"); }
        LocalGameConnection head=open("HEAD",null);
        check(head.getContentLengthLong()==256,"HEAD length");
        try(InputStream in=head.getInputStream()) { check(in.read()==-1,"HEAD has a body"); }
        LocalGameConnection part=open("GET","bytes=4-7");
        check(part.getResponseCode()==206,"range status");
        check("bytes 4-7/256".equals(part.getHeaderField("Content-Range")),"range header");
        try(InputStream in=part.getInputStream()) {
            check(in.available()==4,"range availability");
            check(in.skip(1)==1,"range skip");
            check(Arrays.equals(in.readAllBytes(),new byte[]{5,6,7}),"range leaked adjacent bytes");
            check(in.available()==0,"range EOF");
        }
        LocalGameConnection suffix=open("GET","bytes=-4");
        try(InputStream in=suffix.getInputStream()) {
            check(Arrays.equals(in.readAllBytes(),Arrays.copyOfRange(data,252,256)),"suffix range");
        }
        LocalGameConnection clipped=open("GET","bytes=254-999");
        check(clipped.getContentLengthLong()==2,"range clipped at EOF");
        for(String range:new String[]{"bytes=999-","bytes=9-3","bytes=0-1,4-5","broken"}) {
            LocalGameConnection bad=open("GET",range);
            check(bad.getResponseCode()==416,"invalid range accepted");
            check("bytes */256".equals(bad.getHeaderField("Content-Range")),"invalid range header");
            try { bad.getInputStream(); throw new AssertionError("invalid range body"); }
            catch(IOException expected) {}
        }
        System.out.println("PASS: actual local file GET, HEAD, ranges, skip, EOF and network prohibition");
    }
}
''', encoding='utf-8')
            sources = sorted(str(path) for path in root.rglob('*.java'))
            subprocess.run([str(JAVA / 'javac.exe'), '-d', str(root), *sources], check=True)
            result = subprocess.run([str(JAVA / 'java.exe'), '-cp', str(root),
                                     'com.exvius.local.FileSmoke', str(root)],
                                    text=True, capture_output=True, check=True)
            self.assertIn('PASS:', result.stdout)
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
