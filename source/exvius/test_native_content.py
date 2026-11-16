"""Exercise the approved native content ZIP and actual Java cache installer."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from decode_client_data import client_manifest
from native_master_index import paired_index

def _scratch(root):
    path = root / 'build' / 'scratch'
    path.mkdir(parents=True, exist_ok=True)
    return path


ROOT = Path(__file__).resolve().parents[2]
JAVA = Path('C:/Program Files/Microsoft/jdk-11.0.12.7-hotspot/bin')
JSON_JAR = ROOT / 'tools/vendor/ghidra_11.1.2_PUBLIC/Ghidra/Features/BSim/lib/json-simple-1.1.1.jar'
SPEC = importlib.util.spec_from_file_location('native_content_build', ROOT / 'custom-engine/tools/build_fork.py')
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class NativeContentDelivery(unittest.TestCase):
    def test_actual_archive_bytes_indexes_and_java_install_retry(self):
        with tempfile.TemporaryDirectory(prefix='native-content-test-', dir=_scratch(ROOT)) as scratch:
            work = Path(scratch)
            assets = work / 'assets/rules'
            selected = BUILD.native_content_entries()
            self.assertEqual(BUILD.add_native_content_assets(assets), len(selected))
            quest = json.loads((ROOT / 'source/server/content/quest_chain_repairs.json').read_text(encoding='utf-8'))
            quest_names = {'native/' + item['path'] for item in quest['native_overlay']['files']}
            self.assertEqual(len(quest_names), 13)
            self.assertTrue(quest_names.issubset(selected))
            manifest = json.loads((assets / 'native_content.json').read_text(encoding='utf-8'))
            archive = assets / 'native_content.zip'
            self.assertEqual(sha(archive.read_bytes()), manifest['sha256'])
            expected = {item['path']: item['sha256'] for item in manifest['files']}
            tables = {value['token']: value for value in client_manifest(
                ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()}
            with zipfile.ZipFile(archive) as packed:
                self.assertEqual(set(packed.namelist()), set(selected))
                self.assertEqual(len(packed.namelist()), len(expected))
                self.assertEqual(sum(item.file_size for item in packed.infolist()), manifest['expanded_bytes'])
                for name, source in selected.items():
                    data = packed.read(name)
                    self.assertEqual(data, source)
                    self.assertEqual(expected[name], sha(data))
                    if name.startswith('native/mst/Ver'):
                        token = Path(name).stem.split('_')[1]
                        info = tables[token]
                        pair = paired_index(info['table'], Path(name[7:]), data, info['key'])
                        if pair:
                            self.assertEqual(packed.read('native/' + pair[0].as_posix()), pair[1])
            self.run_actual_java_installer(work, assets.parent)

    def test_packaging_rejects_unapproved_paths_hashes_and_split_pairs(self):
        with tempfile.TemporaryDirectory(prefix='native-content-scope-', dir=_scratch(ROOT)) as scratch:
            root = Path(scratch)
            rules = root / 'rules'
            contract = rules / 'content/quest_chain_repairs.json'
            contract.parent.mkdir(parents=True)
            native = root / 'data/overlay/mst'
            native.mkdir(parents=True)
            (native / 'Ver46_myGc0U5v.dat').write_bytes(b'master')
            (native / 'Ver47_myGc0U5v.dat').write_bytes(b'master')
            (native / 'myGc0U5v.i').write_bytes(b'index')
            master = {'path': 'mst/Ver46_myGc0U5v.dat', 'sha256': sha(b'master')}
            index = {'path': 'mst/myGc0U5v.i', 'sha256': sha(b'index')}
            cases = [
                ([{'path': '../mst/Ver46_myGc0U5v.dat', 'sha256': sha(b'master')}], 'Invalid'),
                ([{'path': 'mst\\Ver46_myGc0U5v.dat', 'sha256': sha(b'master')}], 'Invalid'),
                ([{'path': 'mst/Ver99_unlisted.dat', 'sha256': sha(b'master')}], 'outside'),
                ([{'path': 'common_lang/sd/event/sub31/Ver1_999999999.cpk', 'sha256': sha(b'master')}], 'outside'),
                ([dict(master, sha256='0' * 64), index], 'hash mismatch'),
                ([master], 'Incomplete'),
                ([index], 'Incomplete'),
                ([master, index, dict(master, path='mst/Ver47_myGc0U5v.dat')], 'Incomplete'),
            ]
            with patch.object(BUILD, 'PROJECT', root), patch.object(BUILD, 'RULES_BUNDLE', rules), \
                    patch('approved_native_repairs.build_approved_files', return_value={}):
                for files, error in cases:
                    with self.subTest(files=files):
                        contract.write_text(json.dumps({'native_overlay': {'files': files}}), encoding='utf-8')
                        with self.assertRaisesRegex(ValueError, error):
                            BUILD.native_content_entries()
                contract.write_text(json.dumps({'native_overlay': {'files': [master, index]}}), encoding='utf-8')
                self.assertEqual(set(BUILD.native_content_entries()), {'native/' + master['path'], 'native/' + index['path']})
                ai_contract = rules / 'content/battle/ai_repairs.json'
                ai_contract.parent.mkdir(parents=True)
                (native / 'Ver335_PCm9K3no.dat').write_bytes(b'ai master')
                (native / 'PCm9K3no.i').write_bytes(b'ai index')
                ai_master = {'path': 'mst/Ver335_PCm9K3no.dat', 'sha256': sha(b'ai master')}
                ai_index = {'path': 'mst/PCm9K3no.i', 'sha256': sha(b'ai index')}
                for files in [[ai_master], [ai_index]]:
                    ai_contract.write_text(json.dumps({'native_overlay': {'files': files}}), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'Incomplete'):
                        BUILD.native_content_entries()
                ai_contract.write_text(json.dumps({'native_overlay': {'files': [ai_master, ai_index]}}), encoding='utf-8')
                self.assertEqual(len(BUILD.native_content_entries()), 4)

    def run_actual_java_installer(self, work, assets):
        sources = {
            'android/content/Context.java': '''package android.content;
import java.io.File; import android.content.res.AssetManager;
public class Context {
 private final File files, cache; private final AssetManager assets;
 public Context(File root,File source) { files=new File(root,"files");cache=new File(root,"cache");
  files.mkdirs();cache.mkdirs();assets=new AssetManager(source); }
 public File getFilesDir(){return files;} public File getCacheDir(){return cache;}
 public AssetManager getAssets(){return assets;}
}''',
            'android/content/res/AssetManager.java': '''package android.content.res;
import java.io.*;
public class AssetManager {
 private final File root; public int opens; public boolean corrupt;
 public AssetManager(File f){root=f;}
 public InputStream open(String name)throws IOException { opens++;
  if(corrupt && name.endsWith(".zip"))return new ByteArrayInputStream(new byte[]{1,2,3});
  return new FileInputStream(new File(root,name)); }
}''',
            'android/system/ErrnoException.java': '''package android.system;
public class ErrnoException extends Exception { public ErrnoException(String s){super(s);} }''',
            'android/system/Os.java': '''package android.system;
import java.nio.file.*;
public class Os {
 public static boolean failIndexOnce;
 public static void rename(String from,String to)throws ErrnoException {
  if(failIndexOnce && to.endsWith(".i")){failIndexOnce=false;throw new ErrnoException("injected interrupted install");}
  try{Files.move(Path.of(from),Path.of(to),StandardCopyOption.REPLACE_EXISTING);}
  catch(Exception e){throw new ErrnoException(e.toString());}
 }
}''',
            'org/json/JSONObject.java': '''package org.json;
import java.util.Map; import org.json.simple.JSONValue;
public class JSONObject {
 final Map<?,?> value;
 public JSONObject(String s){this((Map<?,?>)JSONValue.parse(s));}
 JSONObject(Map<?,?> m){if(m==null)throw new IllegalArgumentException("JSON object");value=m;}
 public JSONArray getJSONArray(String k){return new JSONArray((java.util.List<?>)value.get(k));}
 public String getString(String k){return (String)value.get(k);}
 public long getLong(String k){return ((Number)value.get(k)).longValue();}
}''',
            'org/json/JSONArray.java': '''package org.json;
import java.util.*;
public class JSONArray {
 final List<?> value; JSONArray(List<?> v){value=v;}
 public int length(){return value.size();}
 public JSONObject getJSONObject(int i){return new JSONObject((Map<?,?>)value.get(i));}
}''',
            'com/exvius/local/NativeContentSmoke.java': '''package com.exvius.local;
import android.content.Context; import android.system.Os;
import java.io.*; import java.nio.file.*; import java.util.*; import org.json.*;
public class NativeContentSmoke {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static void reset()throws Exception{java.lang.reflect.Field f=NativeContent.class.getDeclaredField("installed");
  f.setAccessible(true);f.setBoolean(null,false);}
 static void intact(Context c,byte[] save)throws Exception{
  check(Arrays.equals(save,Files.readAllBytes(new File(c.getFilesDir(),"exvius/state/campaign.json").toPath())),"save changed");
  try(java.util.stream.Stream<Path> s=Files.walk(c.getFilesDir().toPath())){
   check(s.noneMatch(p->p.toString().endsWith(".installing")),"partial staging left");}
  check(c.getCacheDir().list().length==0,"archive staging left");
 }
 static void verify(Context c,JSONArray files)throws Exception{
  for(int i=0;i<files.length();i++){JSONObject row=files.getJSONObject(i);
   check(DataPack.sha256(DataPack.destination(c.getFilesDir(),row.getString("path"))).equals(row.getString("sha256")),"installed bytes differ");}
 }
 public static void main(String[] a)throws Exception{
  File assets=new File(a[1]);Context c=new Context(new File(a[0],"app"),assets);
  File save=new File(c.getFilesDir(),"exvius/state/campaign.json");save.getParentFile().mkdirs();
  byte[] before="existing save must remain byte identical".getBytes("UTF-8");Files.write(save.toPath(),before);
  JSONObject manifest=new JSONObject(Files.readString(new File(assets,"rules/native_content.json").toPath()));
  JSONArray files=manifest.getJSONArray("files");
  NativeContent.install(c);verify(c,files);int opens=c.getAssets().opens;
  NativeContent.install(c);check(c.getAssets().opens==opens,"same process reinstalled");intact(c,before);
  reset();NativeContent.install(c);check(c.getAssets().opens==opens+1,"valid cache opened archive");
  File index=null;for(int i=0;i<files.length();i++){String path=files.getJSONObject(i).getString("path");
   if(path.endsWith("myGc0U5v.i"))index=DataPack.destination(c.getFilesDir(),path);}
  check(index!=null,"missing seekable index fixture");Files.write(index.toPath(),new byte[]{9,9,9});
  reset();NativeContent.install(c);verify(c,files);intact(c,before);
  Files.delete(index.toPath());Os.failIndexOnce=true;reset();
  try{NativeContent.install(c);throw new AssertionError("partial install acknowledged");}
  catch(IllegalStateException expected){}
  intact(c,before);NativeContent.install(c);verify(c,files);intact(c,before);
  Files.write(index.toPath(),new byte[]{7});c.getAssets().corrupt=true;reset();
  try{NativeContent.install(c);throw new AssertionError("bad archive accepted");}
  catch(IllegalStateException expected){}
  check(Files.readAllBytes(index.toPath())[0]==7,"bad archive wrote files");intact(c,before);
  c.getAssets().corrupt=false;NativeContent.install(c);verify(c,files);intact(c,before);
  for(String bad:new String[]{"native/../exvius/state/campaign.json","native/mst/../../exvius/state/campaign.json","native/mst\\bad"}){
   try{DataPack.destination(c.getFilesDir(),bad);throw new AssertionError("unsafe path accepted");}
   catch(IOException expected){}
  }
  System.out.println("PASS: actual Java native content cold install, cache validation, stale index repair, partial retry, hash rejection and save preservation");
 }
}''',
        }
        java_root = work / 'java'
        for name, source in sources.items():
            target = java_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding='utf-8')
        production = ROOT / 'custom-engine/src/fork-java/com/exvius/local/NativeContent.java'
        (java_root / 'com/exvius/local/NativeContent.java').write_bytes(production.read_bytes())
        data_pack = ROOT / 'source/memorial/android/src/main/java/com/exvius/local/DataPack.java'
        (java_root / 'com/exvius/local/DataPack.java').write_bytes(data_pack.read_bytes())
        java_sources = [str(path) for path in java_root.rglob('*.java')]
        subprocess.run([str(JAVA / 'javac.exe'), '-cp', str(JSON_JAR), '-d', str(java_root), *java_sources], check=True)
        result = subprocess.run([str(JAVA / 'java.exe'), '-cp', str(java_root) + ';' + str(JSON_JAR),
                                 'com.exvius.local.NativeContentSmoke', str(work), str(assets)],
                                text=True, capture_output=True, check=True)
        self.assertIn('PASS:', result.stdout)
        print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
