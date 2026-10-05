package tv.projectivy.plugin.wallpaperprovider.sample

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.content.res.AppCompatResources
import androidx.leanback.app.GuidedStepSupportFragment
import androidx.leanback.widget.GuidanceStylist.Guidance
import androidx.leanback.widget.GuidedAction

class SettingsFragment : GuidedStepSupportFragment() {
    override fun onCreateGuidance(savedInstanceState: Bundle?): Guidance {
        return Guidance(
            getString(R.string.plugin_name),
            "Checks your GitHub wallpaper feed every 15 minutes.",
            "Wallpaper refresh",
            AppCompatResources.getDrawable(requireActivity(), R.drawable.ic_plugin)
        )
    }

    override fun onCreateActions(actions: MutableList<GuidedAction>, savedInstanceState: Bundle?) {
        actions.add(
            GuidedAction.Builder(context)
                .id(ACTION_REFRESH)
                .title("Refresh wallpaper now")
                .description("Fetch the latest score wallpaper from GitHub")
                .build()
        )
    }

    override fun onGuidedActionClicked(action: GuidedAction) {
        if (action.id == ACTION_REFRESH) {
            (requireActivity() as SettingsActivity).requestWallpaperUpdate()
            Toast.makeText(requireContext(), "Wallpaper refresh requested", Toast.LENGTH_SHORT).show()
        }
    }

    companion object {
        private const val ACTION_REFRESH = 1L
    }
}
