package com.exvius.offline.test;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** Local save choices over the original title artwork. */
public final class OfflineMenu {
    private static Activity activity;
    private static FrameLayout cover;
    private static Button resume, fresh;
    private static TextView status;
    private static boolean ready, hasSave, loading;
    private static final Handler ui = new Handler(Looper.getMainLooper());

    private OfflineMenu() {}
    public static volatile int requestedAction;
    public static void choose(int action) { requestedAction = action; }

    private static int dp(int n) {
        return Math.round(n * activity.getResources().getDisplayMetrics().density);
    }

    private static TextView text(String value, int size, int color) {
        TextView view = new TextView(activity);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        return view;
    }

    private static Button button(String label) {
        Button button = new Button(activity);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(21);
        button.setTextColor(Color.WHITE);
        button.setTypeface(null, Typeface.BOLD);
        GradientDrawable background = new GradientDrawable(
            GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0xff165199, 0xff082755});
        background.setCornerRadius(dp(8));
        background.setStroke(dp(2), 0xffb8c6dc);
        button.setBackground(background);
        return button;
    }

    public static void install(Activity owner) {
        activity = owner;
        cover = new FrameLayout(owner);
        cover.setClickable(true);
        // Keep the existing title illustration visible between the two panels.
        LinearLayout top = new LinearLayout(owner);
        top.setOrientation(LinearLayout.VERTICAL);
        top.setGravity(Gravity.CENTER);
        top.setBackgroundColor(Color.WHITE);
        TextView edition = text("OFFLINE EDITION", 15, 0xff476580);
        edition.setLetterSpacing(0.18f);
        top.addView(edition);
        FrameLayout.LayoutParams topParams = new FrameLayout.LayoutParams(-1, 1, Gravity.TOP);
        cover.addView(top, topParams);

        LinearLayout bottom = new LinearLayout(owner);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setGravity(Gravity.CENTER);
        bottom.setPadding(dp(48), dp(12), dp(48), dp(22));
        bottom.setBackgroundColor(Color.WHITE);
        resume = button("Continue");
        fresh = button("New Game");
        LinearLayout.LayoutParams row = new LinearLayout.LayoutParams(-1, dp(56));
        row.setMargins(0, 0, 0, dp(12));
        bottom.addView(resume, row);
        bottom.addView(fresh, new LinearLayout.LayoutParams(row));
        status = text("Preparing local game...", 13, 0xff536a7c);
        bottom.addView(status, new LinearLayout.LayoutParams(-1, dp(30)));
        bottom.addView(text("TEST ONLY 10x", 11, 0xff8b5b24));
        FrameLayout.LayoutParams bottomParams = new FrameLayout.LayoutParams(-1, 1, Gravity.BOTTOM);
        cover.addView(bottom, bottomParams);
        cover.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob) -> {
            int h = b - t;
            if (h == ob - ot) return;
            topParams.height = Math.round(h * 0.23f);
            bottomParams.height = Math.round(h * 0.295f);
            top.setLayoutParams(topParams);
            bottom.setLayoutParams(bottomParams);
        });
        resume.setOnClickListener(v -> begin(false));
        fresh.setOnClickListener(v -> {
            if (hasSave) new AlertDialog.Builder(activity)
                .setTitle("Start a new game?")
                .setMessage("Your current save will be kept as a local backup.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("New Game", (d,w) -> begin(true)).show();
            else begin(true);
        });
        owner.addContentView(cover, new ViewGroup.LayoutParams(-1, -1));
        updateButtons();
        refreshSave();
    }

    private static JSONObject request(boolean reset) throws Exception {
        URL url = new URL("https://v900-lapis.gumi.sg/__exvius/" + (reset ? "new-game" : "status"));
        HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        try {
            if (reset) {
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                try (java.io.OutputStream out = connection.getOutputStream()) {
                    out.write("{\"confirm\":true}".getBytes("UTF-8"));
                }
            }
            if (connection.getResponseCode() != 200) throw new Exception("Local save unavailable");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[1024];
                int n;
                while ((n = input.read(buffer)) != -1) bytes.write(buffer, 0, n);
            }
            return new JSONObject(bytes.toString("UTF-8"));
        } finally { connection.disconnect(); }
    }

    private static void refreshSave() {
        new Thread(() -> {
            try {
                JSONObject save = request(false);
                ui.post(() -> {
                    hasSave = save.optBoolean("has_save");
                    status.setText(hasSave ? "Local save: " + save.optString("name") + "  |  Rank " + save.optInt("rank") : "Your adventure starts here");
                    updateButtons();
                });
            } catch (Exception error) {
                ui.post(() -> { status.setText("Local game service unavailable"); resume.setEnabled(false); fresh.setEnabled(false); });
            }
        }, "ExviusLocalSave").start();
    }

    private static void updateButtons() {
        resume.setEnabled(ready && hasSave && !loading);
        fresh.setEnabled(ready && !loading);
        resume.setAlpha(resume.isEnabled() ? 1f : 0.4f);
        fresh.setAlpha(fresh.isEnabled() ? 1f : 0.4f);
    }

    private static void begin(boolean reset) {
        loading = true;
        status.setText("Loading local game...");
        updateButtons();
        new Thread(() -> {
            try {
                request(reset);
                ui.post(() -> choose(reset ? 2 : 1));
            } catch (Exception error) {
                ui.post(() -> { loading = false; status.setText("Could not open the local save"); updateButtons(); });
            }
        }, "ExviusLocalStart").start();
    }

    public static void titleReady() {
        ui.post(() -> { ready = true; loading = false; cover.setVisibility(View.VISIBLE); updateButtons(); });
    }

    public static void leaveTitle() {
        ui.post(() -> { if (cover != null) cover.setVisibility(View.GONE); });
    }
}
