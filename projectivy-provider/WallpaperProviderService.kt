package tv.projectivy.plugin.wallpaperprovider.sample

import android.app.Service
import android.content.Intent
import android.os.IBinder
import org.json.JSONArray
import tv.projectivy.plugin.wallpaperprovider.api.Event
import tv.projectivy.plugin.wallpaperprovider.api.IWallpaperProviderService
import tv.projectivy.plugin.wallpaperprovider.api.Wallpaper
import tv.projectivy.plugin.wallpaperprovider.api.WallpaperDisplayMode
import tv.projectivy.plugin.wallpaperprovider.api.WallpaperType
import java.net.HttpURLConnection
import java.net.URL

/**
 * Reads the current wallpaper URL from the repo's Overflight-compatible p.json feed.
 * Projectivy requests this provider again after the manifest cache interval (15 minutes).
 */
class WallpaperProviderService : Service() {
    @Volatile private var lastWallpaper: Wallpaper? = null

    override fun onBind(intent: Intent): IBinder = binder

    private val binder = object : IWallpaperProviderService.Stub() {
        override fun getWallpapers(event: Event?): List<Wallpaper> {
            if (event is Event.LauncherIdleModeChanged && !event.isIdle) return emptyList()
            return fetchLatestWallpaper()?.let { listOf(it) }
                ?: lastWallpaper?.let { listOf(it) }
                ?: emptyList()
        }

        override fun getPreferences(): String = ""

        override fun setPreferences(params: String) = Unit
    }

    private fun fetchLatestWallpaper(): Wallpaper? {
        var connection: HttpURLConnection? = null
        return try {
            val feedUrl = URL("$FEED_URL?refresh=${System.currentTimeMillis()}")
            connection = feedUrl.openConnection() as HttpURLConnection
            connection.connectTimeout = 10_000
            connection.readTimeout = 15_000
            connection.setRequestProperty("Cache-Control", "no-cache")
            connection.setRequestProperty("Pragma", "no-cache")
            connection.setRequestProperty("User-Agent", "ShieldSportsProjectivyProvider/1.0")

            val json = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            val entries = JSONArray(json)
            if (entries.length() == 0) return null

            val entry = entries.getJSONObject(0)
            val imageUrl = entry.optString("url_img").takeIf {
                it.startsWith("https://")
            } ?: return null
            val wallpaper = Wallpaper(
                uri = imageUrl,
                type = WallpaperType.IMAGE,
                displayMode = WallpaperDisplayMode.CROP,
                title = entry.optString("title", "Shield Sports"),
                source = "GitHub"
            )
            lastWallpaper = wallpaper
            wallpaper
        } catch (_: Exception) {
            null
        } finally {
            connection?.disconnect()
        }
    }

    companion object {
        private const val FEED_URL =
            "https://stakemillion3-star.github.io/shield-wallpaper/p.json"
    }
}
