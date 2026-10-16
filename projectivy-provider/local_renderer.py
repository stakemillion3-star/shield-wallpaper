"""Run the shared renderer in the app's private workspace, using bundled artwork."""
import hashlib
import importlib
import os
from pathlib import Path


def render(workspace):
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    os.environ['SHIELD_FONT_DIR'] = str(root / 'fonts')
    import generator
    generator = importlib.reload(generator)
    generator.main()
    image = root / 'wallpaper.jpg'
    from PIL import Image
    with Image.open(image) as check:
        check.verify()
    digest = hashlib.sha256(image.read_bytes()).hexdigest()[:16]
    target = root / ('wallpaper-' + digest + '.jpg')
    if not target.exists():
        image.replace(target)
    else:
        image.unlink()
    return str(target)
