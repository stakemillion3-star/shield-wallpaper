from pathlib import Path
import sys

template = Path(sys.argv[1])
service_target = template / "sample/src/main/java/tv/projectivy/plugin/wallpaperprovider/sample/WallpaperProviderService.kt"
manifest = template / "sample/src/main/AndroidManifest.xml"
strings = template / "sample/src/main/res/values/strings.xml"

service_target.write_text(
    (Path(__file__).parent / "WallpaperProviderService.kt").read_text(encoding="utf-8"),
    encoding="utf-8",
)

manifest_text = manifest.read_text(encoding="utf-8")
old_cache = 'android:value="@integer/items_cache_duration_millis"'
if old_cache not in manifest_text:
    raise SystemExit("Projectivy template cache-duration setting changed; review before building.")
manifest.write_text(
    manifest_text.replace(old_cache, 'android:value="900000"'),
    encoding="utf-8",
)

strings_text = strings.read_text(encoding="utf-8")
strings_text = strings_text.replace(
    "<string name=\"plugin_name\">Projectivy Wallpaper Provider Sample</string>",
    "<string name=\"plugin_name\">Shield Sports Live</string>",
).replace(
    "<string name=\"plugin_uuid\">CHANGE_ME</string>",
    "<string name=\"plugin_uuid\">72617f9c-586e-4d40-9250-dc909795a5e9</string>",
)
if "CHANGE_ME" in strings_text:
    raise SystemExit("Plugin UUID replacement failed.")
strings.write_text(strings_text, encoding="utf-8")
