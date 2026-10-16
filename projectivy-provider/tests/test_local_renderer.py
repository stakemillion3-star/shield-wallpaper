import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from PIL import Image

MODULE = Path(__file__).resolve().parents[1] / 'local_renderer.py'
spec = importlib.util.spec_from_file_location('local_renderer_test', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LocalRendererTests(unittest.TestCase):
    def setUp(self):
        self.original = Path.cwd()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        os.chdir(self.original)
        self.temp.cleanup()
    def run_render(self, main):
        fake = types.ModuleType('generator')
        fake.main = main
        with patch.dict('sys.modules', {'generator': fake}), patch.object(module.importlib, 'reload', return_value=fake):
            return Path(module.render(str(self.root)))
    def test_identical_content_keeps_same_uri(self):
        def draw(): Image.new('RGB', (32, 18), 'blue').save('wallpaper.jpg')
        first = self.run_render(draw)
        data = first.read_bytes()
        second = self.run_render(draw)
        self.assertEqual(first, second)
        self.assertEqual(data, second.read_bytes())
    def test_changed_content_gets_new_uri_and_preserves_previous(self):
        first = self.run_render(lambda: Image.new('RGB',(32,18),'blue').save('wallpaper.jpg'))
        second = self.run_render(lambda: Image.new('RGB',(32,18),'red').save('wallpaper.jpg'))
        self.assertNotEqual(first,second)
        self.assertTrue(first.exists())
    def test_bad_output_cannot_replace_last_good(self):
        first = self.run_render(lambda: Image.new('RGB',(32,18),'blue').save('wallpaper.jpg'))
        data=first.read_bytes()
        with self.assertRaises(Exception):
            self.run_render(lambda: Path('wallpaper.jpg').write_text('broken'))
        self.assertEqual(data, first.read_bytes())

if __name__=='__main__': unittest.main()
