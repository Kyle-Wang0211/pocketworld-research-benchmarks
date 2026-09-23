import com.pocketworld.capture.PwXrslamTransport
import java.nio.ByteBuffer

fun check(c: Boolean, m: String) { if (!c) { println("FAIL " + m); System.exit(1) } else println("ok   " + m) }

fun main() {
    val t = PwXrslamTransport()
    val buf = ByteBuffer.allocateDirect(64)
    val create = PwXrslamTransport::class.java.getDeclaredMethod("nativeCreate", String::class.java, String::class.java)
    create.isAccessible = true
    check(create.invoke(t, "slam", "device") as Int == 1, "nativeCreate == 1 (fake core)")
    check(t.pushCameraAndRunRawWithIntrinsics(buf, 1.0, 8, 0, 1, null)[0] == 0.0, "K=null push rc 0")
    var tr = t.intrinsicsTrace()
    check(tr.size == 18 && tr[0] == 0.0, "trace rc 0, 18 values")
    check(tr[2] == 0.0 && tr[13] == 0.0 && tr[14] == 1.0 && tr[15] == 0.0, "K=null: not attached, not rejected")
    val k = doubleArrayOf(449.2647705078125, 449.2647705078125, 318.82309977213544, 239.3213907877604)
    check(t.pushCameraAndRunRawWithIntrinsics(buf, 2.0, 8, 0, 1, k)[0] == 0.0, "K push rc 0")
    tr = t.intrinsicsTrace()
    check(tr[1] == 2.0 && tr[2] == 1.0 && tr[3] == 1.0, "K: seq 2, attached, report read")
    check(tr[5] == k[0] && tr[6] == k[1] && tr[7] == k[2] && tr[8] == k[3], "K bit-exact through JNI")
    check(tr[4] == 1.0 && tr[16] == 1.0 && tr[17] == 0.0, "fake config-only core: report differs (proven not taken), equal 0")
    val r2 = t.pushCameraAndRunRawWithIntrinsics(buf, 3.0, 8, 0, 1, doubleArrayOf(1.0, 2.0, 3.0))
    check(r2[0] == 0.0, "length-3 K: frame still pushed (rc 0)")
    tr = t.intrinsicsTrace()
    check(tr[1] == 3.0, "length-3 K: camera sequence advanced (frame reached the core)")
    check(tr[2] == 0.0 && tr[14] == 2.0 && tr[15] == 1.0, "length-3 K: not attached, counted rejected_invalid")
    val r3 = t.pushCameraAndRunRawWithIntrinsics(buf, 4.0, 8, 0, 1, doubleArrayOf(1.0, 2.0, 3.0, 4.0, 5.0))
    check(r3[0] == 0.0 && t.intrinsicsTrace()[15] == 2.0, "length-5 K: pushed, rejected_invalid 2")
    check(t.pushCameraAndRunRaw(buf, 5.0, 8, 0, 1)[0] == 0.0 && t.intrinsicsTrace()[14] == 4.0, "legacy entry still works, counted not_attached")
    println("host JNI smoke: PASS")
}
