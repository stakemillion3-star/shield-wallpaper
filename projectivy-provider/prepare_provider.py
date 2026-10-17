from pathlib import Path
import sys
import os

template = Path(sys.argv[1])
source_dir = Path(__file__).parent
java_dir = template / "sample/src/main/java/tv/projectivy/plugin/wallpaperprovider/sample"
service_target = java_dir / "WallpaperProviderService.kt"
settings_target = java_dir / "SettingsFragment.kt"
manifest = template / "sample/src/main/AndroidManifest.xml"
strings = template / "sample/src/main/res/values/strings.xml"

for target, source in (
    (service_target, source_dir / "WallpaperProviderService.kt"),
    (settings_target, source_dir / "SettingsFragment.kt"),
):
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

manifest_text = manifest.read_text(encoding="utf-8")
old_cache = 'android:value="@integer/items_cache_duration_millis"'
if old_cache not in manifest_text:
    raise SystemExit("Projectivy template cache-duration setting changed; review before building.")
manifest.write_text(
    manifest_text.replace(old_cache, 'android:value="60000"'),
    encoding="utf-8",
)

strings_text = strings.read_text(encoding="utf-8")
strings_text = strings_text.replace(
    "<string name=\"plugin_name\">Projectivy Wallpaper Provider Sample</string>",
    "<string name=\"plugin_name\">Shield Sports Live</string>",
).replace(
    "<string name=\"plugin_uuid\">CHANGE_ME</string>",
    "<string name=\"plugin_uuid\">72617f9c-586e-4d40-9250-dc909795a5e9</string>",
).replace(
    "<string name=\"plugin_description\">Plugin description</string>",
    "<string name=\"plugin_description\">Live Bosnia and Raptors wallpaper from your GitHub feed</string>",
)
if "CHANGE_ME" in strings_text:
    raise SystemExit("Plugin UUID replacement failed.")
strings.write_text(strings_text, encoding="utf-8")

# The template passes an Android resource ID, but Projectivy requires the UUID string.
activity = java_dir / "SettingsActivity.kt"
activity_text = activity.read_text(encoding="utf-8")
old_provider_id = "putExtra(WallpaperProviderContract.EXTRA_PROVIDER_ID, R.string.plugin_uuid)"
if old_provider_id not in activity_text:
    raise SystemExit("Projectivy template refresh broadcast changed; review before building.")
activity.write_text(
    activity_text.replace(old_provider_id,
        "putExtra(WallpaperProviderContract.EXTRA_PROVIDER_ID, getString(R.string.plugin_uuid))"),
    encoding="utf-8",
)

# Bundle the existing renderer instead of depending on delayed GitHub jobs.
import shutil
repo = source_dir.parent
python_dir = template / "sample/src/main/python"
python_dir.mkdir(parents=True, exist_ok=True)
for source in (repo / "generator.py", source_dir / "local_renderer.py"):
    shutil.copy2(source, python_dir / source.name)
asset_dir = template / "sample/src/main/assets/shield"
asset_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(repo / "assets/background.jpg", asset_dir / "background.jpg")
shutil.copy2(repo / "wallpaper.jpg", asset_dir / "bootstrap.jpg")
shutil.copy2(source_dir / "DejaVu-LICENSE.txt", asset_dir / "DejaVu-LICENSE.txt")
font_root = Path(os.environ.get("SHIELD_BUILD_FONT_DIR", "/usr/share/fonts/truetype/dejavu"))
for font_name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
    shutil.copy2(font_root / font_name, asset_dir / font_name)

manifest_text = manifest.read_text(encoding="utf-8")
manifest_text = manifest_text.replace("<application", '<uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" tools:ignore="ProtectedPermissions" /><application', 1)
manifest_text = manifest_text.replace("</application>", '''
        <provider android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.wallpapers"
            android:exported="false" android:grantUriPermissions="true">
            <meta-data android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/wallpaper_paths" />
        </provider>
    </application>''')
manifest.write_text(manifest_text, encoding="utf-8")
xml_dir = template / "sample/src/main/res/xml"
xml_dir.mkdir(parents=True, exist_ok=True)
(xml_dir / "wallpaper_paths.xml").write_text('<paths><files-path name="wallpapers" path="wallpaper/" /></paths>', encoding="utf-8")

build = template / "sample/build.gradle.kts"
text = build.read_text(encoding="utf-8")
text = text.replace("plugins {", 'plugins {\n    id("com.chaquo.python") version "17.1.0"', 1)
text += '''
android {
    defaultConfig {
        minSdk = 24
        versionCode = 6
        versionName = "2.2-resume"
        ndk { abiFilters += listOf("arm64-v8a") }
    }
}
chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            install("Pillow==11.0.0")
            install("requests==2.32.5")
            install("tzdata")
        }
    }
}
'''
build.write_text(text, encoding="utf-8")
