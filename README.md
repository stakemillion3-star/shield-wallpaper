# Shield Sports Wallpaper

Automatic 4K (3840×2160) Projectivy Launcher wallpaper for an NVIDIA Shield.

## v1
- Bosnia & Herzegovina: last result + next three UEFA Nations League fixtures
- Toronto Raptors: last result + next three games
- Times are rendered in America/Toronto (Eastern Time)
- Refreshes every 3 hours with GitHub Actions
- If a feed fails, the renderer shows a neutral unavailable state rather than inventing a score or fixture.

## Data
The generator currently reads ESPN's structured sports schedule feeds and only prints scores for events the feed marks completed. The design intentionally fails closed if data cannot be retrieved. We can add an additional validation source before enabling more competitions.

## Artwork
Place the cinematic Bosnia → water/bridge → Toronto background at `assets/background.jpg`. If it is absent, the renderer uses a simple blue/red fallback background.

## Projectivy URL
After the first successful Action run, use:

`https://stakemillion3-star.github.io/shield-wallpaper/wallpaper.jpg`

GitHub Pages is configured from the main branch root.
