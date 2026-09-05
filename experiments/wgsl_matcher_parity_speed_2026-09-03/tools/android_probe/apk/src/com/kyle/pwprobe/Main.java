package com.kyle.pwprobe;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
import java.io.File;
// 以 app 身份(而不是 adb shell 的 uid 2000)跑同一份探针:麒麟 970 的 Vulkan ICD
// 对 shell 进程不暴露物理设备(vkEnumeratePhysicalDevices 返回 0)。
// 参数从 intent extras 来:rows / reps / kernel(env 名的值);夹具在 files/fixtures/fx13。
public class Main extends Activity {
  static { System.loadLibrary("pwprobe"); }
  public static native String run(String fixDir, int rows, int reps, String kernel, String extraEnv, String outPath);
  @Override protected void onCreate(Bundle b) {
    super.onCreate(b);
    TextView tv = new TextView(this); setContentView(tv);
    final int rows = getIntent().getIntExtra("rows", 8192);
    final int reps = getIntent().getIntExtra("reps", 2);
    final String kernel = getIntent().getStringExtra("kernel") == null ? "" : getIntent().getStringExtra("kernel");
    final String extra = getIntent().getStringExtra("extra") == null ? "" : getIntent().getStringExtra("extra");
    final File fx = new File(getFilesDir(), "fixtures/fx13");
    final File out = new File(getFilesDir(), "probe_out.txt");
    tv.setText("running rows=" + rows + " reps=" + reps + " kernel=" + kernel);
    new Thread(() -> {
      final String r = run(fx.getAbsolutePath(), rows, reps, kernel, extra, out.getAbsolutePath());
      runOnUiThread(() -> tv.setText(r));
    }).start();
  }
}
