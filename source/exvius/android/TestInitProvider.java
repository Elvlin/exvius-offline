package com.exvius.offline.test;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;

/** App-local startup for the separately labelled 10x test APK. */
public final class TestInitProvider extends ContentProvider {
    @Override public boolean onCreate() {
        System.loadLibrary("exviustest");
        return true;
    }
    @Override public Cursor query(Uri uri, String[] columns, String selection,
                                  String[] arguments, String order) { return null; }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] arguments) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection,
                                String[] arguments) { return 0; }
}
