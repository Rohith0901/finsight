package com.finsight.finsight

import android.Manifest
import android.content.pm.PackageManager
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Telephony
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executors

/**
 * SMS access for FinSight, without third-party plugins (ADR-002).
 *
 * finsight/sms        hasPermission, requestPermission, readInbox(since, limit)
 * finsight/sms_events emits whenever the SMS inbox changes while the app is open
 *
 * Messages from personal phone numbers are skipped here, so their text never
 * reaches the Dart side. Nothing is written to disk.
 */
class MainActivity : FlutterActivity() {
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var pendingPermission: MethodChannel.Result? = null
    private var observer: ContentObserver? = null
    private val personal = Regex("^\\+?[0-9]{10,13}$")

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "finsight/sms")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "hasPermission" -> result.success(hasPermission())
                    "requestPermission" -> requestPermission(result)
                    "readInbox" -> {
                        if (!hasPermission()) {
                            result.error("no_permission", "READ_SMS not granted", null)
                        } else {
                            val since = (call.argument<Number>("since") ?: 0).toLong()
                            val limit = (call.argument<Number>("limit") ?: 500).toInt()
                            io.execute {
                                try {
                                    val rows = readInbox(since, limit)
                                    main.post { result.success(rows) }
                                } catch (e: Exception) {
                                    main.post { result.error("read_failed", e.javaClass.simpleName, null) }
                                }
                            }
                        }
                    }
                    else -> result.notImplemented()
                }
            }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, "finsight/sms_events")
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
                    if (!hasPermission()) return
                    // A hot restart listens again without cancelling first.
                    observer?.let { contentResolver.unregisterContentObserver(it) }
                    val obs = object : ContentObserver(main) {
                        override fun onChange(selfChange: Boolean) {
                            events.success(System.currentTimeMillis())
                        }
                    }
                    contentResolver.registerContentObserver(Telephony.Sms.CONTENT_URI, true, obs)
                    observer = obs
                }

                override fun onCancel(arguments: Any?) {
                    observer?.let { contentResolver.unregisterContentObserver(it) }
                    observer = null
                }
            })
    }

    private fun hasPermission(): Boolean =
        checkSelfPermission(Manifest.permission.READ_SMS) == PackageManager.PERMISSION_GRANTED

    private fun requestPermission(result: MethodChannel.Result) {
        if (hasPermission()) {
            result.success(true)
            return
        }
        // Only one request can be in flight; answer an older caller first.
        pendingPermission?.success(false)
        pendingPermission = result
        requestPermissions(arrayOf(Manifest.permission.READ_SMS), REQUEST_SMS)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_SMS) {
            val granted = grantResults.isNotEmpty() &&
                grantResults[0] == PackageManager.PERMISSION_GRANTED
            pendingPermission?.success(granted)
            pendingPermission = null
        }
    }

    /**
     * Messages newer than [since], oldest first. A page holds at least [limit]
     * messages and never ends between two that share a timestamp, so the
     * caller can page with `since = last date` without skipping any.
     */
    private fun readInbox(since: Long, limit: Int): List<Map<String, Any>> {
        val out = ArrayList<Map<String, Any>>()
        var lastDate = Long.MIN_VALUE
        val projection = arrayOf(Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE)
        contentResolver.query(
            Telephony.Sms.Inbox.CONTENT_URI,
            projection,
            "${Telephony.Sms.DATE} > ?",
            arrayOf(since.toString()),
            "${Telephony.Sms.DATE} ASC"
        )?.use { c ->
            val iAddress = c.getColumnIndexOrThrow(Telephony.Sms.ADDRESS)
            val iBody = c.getColumnIndexOrThrow(Telephony.Sms.BODY)
            val iDate = c.getColumnIndexOrThrow(Telephony.Sms.DATE)
            while (c.moveToNext()) {
                val date = c.getLong(iDate)
                if (out.size >= limit && date != lastDate) break
                val address = c.getString(iAddress) ?: continue
                val compact = address.replace(" ", "").replace("-", "")
                if (personal.matches(compact)) continue // personal messages stay on Android's side
                out.add(mapOf(
                    "address" to address,
                    "body" to (c.getString(iBody) ?: ""),
                    "date" to date
                ))
                lastDate = date
            }
        }
        return out
    }

    override fun onDestroy() {
        observer?.let { contentResolver.unregisterContentObserver(it) }
        io.shutdown()
        super.onDestroy()
    }

    companion object {
        private const val REQUEST_SMS = 4021
    }
}
