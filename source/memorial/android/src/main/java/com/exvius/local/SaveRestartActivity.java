package com.exvius.local;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Process;
import android.util.Log;

/** Foreground restart handoff. This process never loads libgame or draws save-management UI. */
public final class SaveRestartActivity extends Activity {
    private final Handler main = new Handler();
    private final java.util.concurrent.ExecutorService worker = java.util.concurrent.Executors.newSingleThreadExecutor();
    private int checks;
    private boolean installed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        installed = state != null && state.getBoolean("installed");
        main.postDelayed(() -> worker.execute(this::handoff), 300);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("installed", installed); super.onSaveInstanceState(state);
    }

    private void handoff() {
        if (installed) { openGame(); return; }
        try {
            int pid = getIntent().getIntExtra("pid", -1);
            if (pid <= 0 || pid == Process.myPid()) throw new IllegalStateException("Invalid game process");
            ActivityManager manager = (ActivityManager)getSystemService(ACTIVITY_SERVICE);
            boolean alive = false;
            java.util.List<ActivityManager.RunningAppProcessInfo> processes = manager.getRunningAppProcesses();
            if (processes == null) throw new IllegalStateException("Unable to inspect game process");
            for (ActivityManager.RunningAppProcessInfo process : processes) {
                if (process.pid != pid) continue;
                if (process.uid != Process.myUid() || !getPackageName().equals(process.processName))
                    throw new IllegalStateException("Unexpected game process");
                alive = true; Process.killProcess(pid);
            }
            if (alive) {
                if (++checks > 100) throw new IllegalStateException("The previous game process has not stopped");
                main.postDelayed(() -> worker.execute(this::handoff), 100); return;
            }
            try {
                android.system.Os.kill(pid, 0);
                if (++checks > 100) throw new IllegalStateException("The previous game process has not exited");
                main.postDelayed(() -> worker.execute(this::handoff), 100); return;
            } catch (android.system.ErrnoException error) {
                if (error.errno != android.system.OsConstants.ESRCH) throw error;
            }
            if (getIntent().getBooleanExtra("delete", false)) SaveSlots.recoverDelete(this);
            else if (getIntent().getBooleanExtra("import", false)) SaveTransferActivity.install(this);
            else SaveSlots.select(this, getIntent().getIntExtra("slot", 0), getIntent().getBooleanExtra("create", false));
            installed = true; openGame();
        } catch (Exception error) {
            Log.e("SaveRestartActivity", error.getClass().getName() + ": " + error.getMessage(), error);
            // The next main-process initialization owns the existing recovery journals.
            openGame();
        }
    }

    private void openGame() {
        runOnUiThread(this::launchGame);
    }
    private void launchGame() {
        try {
            Intent game = new Intent().setClassName(getPackageName(), "com.square_enix.android_googleplay.FFBEWW.Lapis");
            game.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            startActivity(game); finish();
        } catch (RuntimeException error) {
            Log.e("SaveRestartActivity", error.getClass().getName() + ": " + error.getMessage(), error);
            finish();
        }
    }

    @Override public void onBackPressed() { /* Keep the controller visible until the file handoff is complete. */ }
    @Override protected void onDestroy() { main.removeCallbacksAndMessages(null); worker.shutdown(); super.onDestroy(); }
}
