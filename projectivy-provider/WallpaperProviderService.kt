package tv.projectivy.plugin.wallpaperprovider.sample

import android.app.Service
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
        // A bound provider remains active while Projectivy uses it. No always-on computer needed.
        worker.scheduleWithFixedDelay({ render() }, 0, 60, TimeUnit.SECONDS)
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
            if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
            val path = Python.getInstance().getModule("local_renderer")
                .callAttr("render", workspace.absolutePath).toString()
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
            Log.i("ShieldSports", "Local render complete: ${file.name}; changed=$changed")
            // Retain recent images so in-flight Projectivy reads keep working.
            workspace.listFiles()?.filter { it.name.startsWith("wallpaper-") && it.extension == "jpg" }
                ?.sortedByDescending { it.lastModified() }?.drop(4)?.forEach { it.delete() }
        } catch (error: Exception) {
            Log.e("ShieldSports", "Local render failed; keeping last good wallpaper", error)
        }
    }

    override fun onBind(intent: Intent): IBinder = binder
    private val binder = object : IWallpaperProviderService.Stub() {
        override fun getWallpapers(event: Event?): List<Wallpaper> = current?.let { listOf(it) } ?: emptyList()
        override fun getPreferences(): String = ""
        override fun setPreferences(params: String) = Unit
    }
    override fun onDestroy() {
        worker.shutdownNow()
        super.onDestroy()
    }
}
