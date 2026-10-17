package tv.projectivy.plugin.wallpaperprovider.sample

import android.app.Service
import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.IntentFilter
import android.os.PowerManager
import android.os.Process
import android.os.SystemClock
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.concurrent.ScheduledFuture
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.content.FileProvider
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import tv.projectivy.plugin.wallpaperprovider.api.Event
import tv.projectivy.plugin.wallpaperprovider.api.IWallpaperProviderService
import tv.projectivy.plugin.wallpaperprovider.api.Wallpaper
import tv.projectivy.plugin.wallpaperprovider.api.WallpaperType
import tv.projectivy.plugin.wallpaperprovider.api.WallpaperProviderContract
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Renders the shared artwork locally. Network and image work never block Binder calls. */
class WallpaperProviderService : Service() {
    private val worker = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var current: Wallpaper? = null
    private lateinit var workspace: File
    private var pending: ScheduledFuture<*>? = null
    private var nextCheckAt = 0L
    private var lastQuery = 0L
    private var visibilityRetry: ScheduledFuture<*>? = null
    private var foregroundPackage: String? = null
    private var foregroundClass: String? = null
    private var revision = ""
    @Volatile private var destroyed = false
    private val screenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == Intent.ACTION_SCREEN_OFF) {
                synchronized(this@WallpaperProviderService) {
                    pending?.cancel(true)
                    pending = null
                    visibilityRetry?.cancel(false)
                    visibilityRetry = null
                }
                Log.i("ShieldSports", "Paused: screen off")
            } else if (intent.action == Intent.ACTION_SCREEN_ON) {
                synchronized(this@WallpaperProviderService) { lastQuery = 0L }
                requestCheck(3)
            }
        }
    }

    /** Used by both the worker and Python before each network/drawing stage. */
    @Synchronized fun isAllowed(): Boolean {
        if (destroyed || Thread.currentThread().isInterrupted) return false
        if (!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive) return false
        val ops = getSystemService(APP_OPS_SERVICE) as AppOpsManager
        if (ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(), packageName) != AppOpsManager.MODE_ALLOWED) return false
        val now = System.currentTimeMillis()
        // Usage events can become queryable AFTER a previous query's end time.
        // Replay an overlapping window so a delayed Home resume cannot be lost.
        val start = if (lastQuery == 0L) now - TimeUnit.DAYS.toMillis(1)
            else now - TimeUnit.MINUTES.toMillis(2)
        val events = (getSystemService(USAGE_STATS_SERVICE) as UsageStatsManager).queryEvents(start, now)
        val event = UsageEvents.Event()
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            when (event.eventType) {
                UsageEvents.Event.ACTIVITY_RESUMED -> {
                    foregroundPackage = event.packageName
                    foregroundClass = event.className
                }
                UsageEvents.Event.ACTIVITY_PAUSED -> {
                    if (foregroundPackage == event.packageName && foregroundClass == event.className) {
                        foregroundPackage = null
                        foregroundClass = null
                    }
                }
            }
        }
        lastQuery = now
        return foregroundPackage == "com.spocky.projengmenu" &&
            foregroundClass == "com.spocky.projengmenu.ui.home.MainActivity"
    }

    @Synchronized private fun requestCheck(settleRetries: Int = 0) {
        if (!isAllowed()) {
            // Only briefly retry after a launcher callback; never poll indefinitely
            // while another app is foreground. Android may still be recording resume.
            val awake = (getSystemService(POWER_SERVICE) as PowerManager).isInteractive
            if (!destroyed && awake && settleRetries > 0 && visibilityRetry?.isDone != false) {
                visibilityRetry = worker.schedule({
                    synchronized(this) { visibilityRetry = null }
                    requestCheck(settleRetries - 1)
                }, 750, TimeUnit.MILLISECONDS)
            }
            return
        }
        visibilityRetry?.cancel(false)
        visibilityRetry = null
        if (pending?.isDone == false) return
        val delay = maxOf(0L, nextCheckAt - SystemClock.elapsedRealtime())
        pending = worker.schedule({
            if (!isAllowed()) {
                synchronized(this) { pending = null }
                Log.i("ShieldSports", "Paused: Projectivy Home is not visible")
                requestCheck(3)
                return@schedule
            }
            render()
            synchronized(this) {
                pending = null
                nextCheckAt = SystemClock.elapsedRealtime() + 60_000L
            }
            // No repeating task remains after Home is no longer visible.
            requestCheck()
        }, delay, TimeUnit.MILLISECONDS)
    }

    override fun onCreate() {
        super.onCreate()
        workspace = File(filesDir, "wallpaper").apply { mkdirs() }
        copyAsset("background.jpg", File(workspace, "assets/background.jpg"))
        copyAsset("DejaVuSans.ttf", File(workspace, "fonts/DejaVuSans.ttf"))
        copyAsset("DejaVuSans-Bold.ttf", File(workspace, "fonts/DejaVuSans-Bold.ttf"))
        val prefs = getSharedPreferences("local_renderer", MODE_PRIVATE)
        val saved = prefs.getString("image_path", null)?.let { File(it) }
        val initial = saved?.takeIf { it.isFile && it.parentFile == workspace }
            ?: File(workspace, "wallpaper-bootstrap.jpg").also { copyAsset("bootstrap.jpg", it) }
        current = wallpaper(initial)
        revision = assets.open("chaquopy/build.json").bufferedReader().use {
            JSONObject(it.readText()).getJSONObject("assets").getString("app.imy")
        }
        ContextCompat.registerReceiver(this, screenReceiver,
            IntentFilter().apply { addAction(Intent.ACTION_SCREEN_OFF); addAction(Intent.ACTION_SCREEN_ON) },
            ContextCompat.RECEIVER_NOT_EXPORTED)
        requestCheck(3)
    }

    private fun copyAsset(name: String, target: File) {
        target.parentFile?.mkdirs()
        assets.open("shield/$name").use { input -> target.outputStream().use { input.copyTo(it) } }
    }

    private fun wallpaper(file: File): Wallpaper {
        val uri = FileProvider.getUriForFile(this, "$packageName.wallpapers", file)
        grantUriPermission("com.spocky.projengmenu", uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        return Wallpaper(uri = uri.toString(), type = WallpaperType.IMAGE,
            title = "Shield Sports", source = "ESPN · rendered on Shield")
    }

    private fun render() {
        try {
            if (!isAllowed()) return
            if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
            val path = Python.getInstance().getModule("local_renderer")
                .callAttr("render", workspace.absolutePath, this, revision).toString()
            if (path.isBlank() || !isAllowed()) return
            val file = File(path)
            val next = wallpaper(file)
            val changed = current?.uri != next.uri
            current = next
            getSharedPreferences("local_renderer", MODE_PRIVATE).edit()
                .putString("image_path", path).putLong("last_success", System.currentTimeMillis()).apply()
            if (changed) {
                sendBroadcast(Intent(WallpaperProviderContract.ACTION_WALLPAPER_PROVIDER_UPDATED).apply {
                    setPackage("com.spocky.projengmenu")
                    putExtra(WallpaperProviderContract.EXTRA_PROVIDER_ID, getString(R.string.plugin_uuid))
                    putExtra(WallpaperProviderContract.EXTRA_UPDATE_REASON, WallpaperProviderContract.UpdateReason.DATA_CHANGED)
                })
            }
            Log.i("ShieldSports", "Visible-home check complete: ${file.name}; changed=$changed")
            // Retain recent images so in-flight Projectivy reads keep working.
            workspace.listFiles()?.filter { it.name.startsWith("wallpaper-") && it.extension == "jpg" }
                ?.sortedByDescending { it.lastModified() }?.drop(4)?.forEach { it.delete() }
        } catch (error: Exception) {
            if (isAllowed()) Log.e("ShieldSports", "Local check failed; keeping last good wallpaper", error)
            else Log.i("ShieldSports", "Paused: stopped local check after leaving Home")
        }
    }

    override fun onBind(intent: Intent): IBinder {
        requestCheck(3)
        return binder
    }
    override fun onUnbind(intent: Intent): Boolean {
        synchronized(this) {
            pending?.cancel(true); pending = null
            visibilityRetry?.cancel(false); visibilityRetry = null
        }
        return true
    }
    override fun onRebind(intent: Intent) { requestCheck(3) }
    private val binder = object : IWallpaperProviderService.Stub() {
        override fun getWallpapers(event: Event?): List<Wallpaper> {
            requestCheck(3)
            return current?.let { listOf(it) } ?: emptyList()
        }
        override fun getPreferences(): String = ""
        override fun setPreferences(params: String) = Unit
    }
    override fun onDestroy() {
        destroyed = true
        unregisterReceiver(screenReceiver)
        worker.shutdownNow()
        super.onDestroy()
    }
}
