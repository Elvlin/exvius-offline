package com.exvius.local;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

/** First-install data download; subsequent launches go straight to the game. */
public final class DataDownloadActivity extends Activity implements DataUpdates.Progress {
    private TextView status;
    private ProgressBar progress;
    private Button retry;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (DataUpdates.ready(this) && (!DataUpdates.hasPending(this) || DataUpdates.gameOpened())) {
            DataUpdates.checkInBackground(this);
            openGame();
            return;
        }
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        page.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText("Exvius Offline");
        title.setTextSize(28);
        title.setGravity(Gravity.CENTER);
        page.addView(title);
        status = new TextView(this);
        status.setText("Preparing the complete game data download.\nAfter setup, you can play offline.");
        status.setTextSize(17);
        status.setGravity(Gravity.CENTER);
        status.setPadding(0, padding, 0, padding);
        page.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(1000);
        page.addView(progress, new LinearLayout.LayoutParams(-1, -2));
        retry = new Button(this);
        retry.setText("Retry");
        retry.setVisibility(View.GONE);
        retry.setOnClickListener(view -> { retry.setVisibility(View.GONE); DataUpdates.prepare(this, this); });
        page.addView(retry);
        setContentView(page);
        DataUpdates.prepare(this, this);
    }

    private void openGame() {
        Intent game = new Intent();
        game.setClassName(getPackageName(), "com.square_enix.android_googleplay.FFBEWW.Lapis");
        startActivity(game);
        finish();
    }
    @Override public void onDestroy() {
        DataUpdates.detach(this);
        super.onDestroy();
    }

    @Override public void update(String message, long done, long total) {
        runOnUiThread(() -> {
            if (isFinishing()) return;
            status.setText(message);
            progress.setIndeterminate(total <= 0);
            if (total > 0) progress.setProgress((int) Math.min(1000, done * 1000 / total));
        });
    }
    @Override public void complete() { runOnUiThread(() -> { if (!isFinishing()) openGame(); }); }
    @Override public void failed(String message) {
        runOnUiThread(() -> {
            if (isFinishing()) return;
            status.setText(message);
            progress.setIndeterminate(false);
            retry.setVisibility(View.VISIBLE);
        });
    }
}
