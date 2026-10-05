# Shield Sports Live for Projectivy

This companion provider reads the existing Overflight-compatible feed at:

`https://stakemillion3-star.github.io/shield-wallpaper/p.json`

It asks Projectivy to re-request the feed every 15 minutes while Projectivy is refreshing wallpapers. Each request uses a cache-busting query on the JSON feed; the image URL already carries the rendered image hash.

## Build

The GitHub Actions workflow builds the Android TV APK from the official Projectivy wallpaper-provider template and publishes it at:

`downloads/ShieldSportsLive.apk`

The APK can be sideloaded onto the Shield. Install the app, then select **Shield Sports Live** under Projectivy Settings → Appearance → Wallpaper. Keep Overflight installed until the new provider has been tested; you can switch back to Overflight at any time.

## Refresh limits

This is a 15-minute polling interval, not a push notification from GitHub. The image refreshes while Projectivy requests wallpaper updates; it cannot display a new wallpaper while another app is covering the launcher or while the Shield is off. When the Shield returns to Projectivy, its next provider request reads the latest feed.

## Attribution

The Android provider is built from the Projectivy Wallpaper Provider sample template (Apache-2.0): https://github.com/spocky/projectivy-plugin-wallpaper-provider
