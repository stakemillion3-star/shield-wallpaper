# Shield Sports Live — local rendering

This provider runs the repository’s shared `generator.py` on the Shield itself using Chaquopy. It bundles the same background and DejaVu fonts used by GitHub. It reads ESPN directly, renders once per minute after the previous render finishes while the bound provider is active, and notifies Projectivy whenever the image changes. Projectivy polls the provider every minute as a fallback. Images are served through a private FileProvider with read access granted to Projectivy, avoiding remote image cache failures.

The last good image persists across restarts. The existing published wallpaper is bundled for initial startup. Network failures retain the last successful render. The update target is under five minutes after ESPN’s API changes while the Shield is awake and Projectivy is active; this is not a guarantee during network outages, device sleep, or delayed ESPN data. No PC, NAS, or GitHub job is required for normal updates.

## Build

The build workflow uses the official Projectivy template, Python 3.11, Chaquopy 17.1, and Pillow 11.0 (available as an Android wheel). `prepare_provider.py` bundles the shared renderer and assets. Linux builds read fonts from `/usr/share/fonts/truetype/dejavu`; local builds can set `SHIELD_BUILD_FONT_DIR`. APK updates must use the same signing key as the installed app. Keep signing keys out of the repository.

Future renderer/rule changes require an updated APK. GitHub continues publishing its wallpaper independently as a fallback. Android logs tagged `ShieldSports` report each successful render and failures.

The provider retains the existing package and UUID so the selected Projectivy source stays the same. It never changes the default launcher or Home-button mapping.

## Attribution

Projectivy provider template: https://github.com/spocky/projectivy-plugin-wallpaper-provider (Apache-2.0). Python runtime: https://chaquo.com/chaquopy/. Fonts and renderer artwork retain their original licenses.

## Foreground-only efficiency

The provider requires Android Usage Access solely to determine whether Projectivy's Home activity is visible. It fails closed if that access is missing. Device sleep cancels pending work. A scheduled visibility check which finds another app stops the update chain; Home callbacks resume it. No sports fetch or image composition is started outside Home. Work already in progress checks visibility before each request and drawing stage and abandons publication when Home is no longer visible. An already issued network request can take up to its timeout to return.

Each visible-home check fetches display data, compares a persisted signature of the actual cards/standings/time labels, and skips image composition when unchanged. NBA clock ticks do not trigger redraws because the clock is not displayed. Source revision changes invalidate the signature. Team-logo thumbnails are cached locally. A valid previous image and signature survive process restarts. The last-known image stays displayed while paused.
