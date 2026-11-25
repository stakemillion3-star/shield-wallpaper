import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
spec=importlib.util.spec_from_file_location('logo_generator',Path(__file__).resolve().parents[2]/'generator.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class TeamLogoTests(unittest.TestCase):
    def setUp(self):g.NBA_LOGOS.clear()
    def test_all_thirty_teams_have_fallback(self):
        self.assertEqual(len(set(g.TEAM_ABBR.values())),30)
        self.assertEqual(g.TEAM_ABBR['Brooklyn Nets'],'bkn')
    def test_nets_without_standings_uses_fallback(self):
        icon=Image.new('RGBA',(30,30))
        with patch.object(g,'remote_image',return_value=icon) as fetch:
            self.assertIs(g.team_icon('Brooklyn Nets','nba'),icon)
        self.assertIn('/bkn.png',fetch.call_args.args[0])
    def test_failed_feed_url_uses_fallback(self):
        g.NBA_LOGOS['Brooklyn Nets']='https://example.invalid/logo.png'
        icon=Image.new('RGBA',(30,30))
        with patch.object(g,'remote_image',side_effect=[None,icon]) as fetch:
            self.assertIs(g.team_icon('Brooklyn Nets','nba'),icon)
        self.assertEqual(fetch.call_count,2)
    def test_failed_download_does_not_publish_blank_logo(self):
        with patch.object(g,'remote_image',return_value=None),self.assertRaises(RuntimeError):
            g.team_icon('Brooklyn Nets','nba')
    def test_event_logo_is_collected_without_standings(self):
        g.parse_event({'date':'2026-11-25T00:00Z','competitions':[{'competitors':[{'team':{'displayName':'Brooklyn Nets','logo':'https://example.com/nets.png'}}]}]})
        self.assertEqual(g.NBA_LOGOS['Brooklyn Nets'],'https://example.com/nets.png')
if __name__=='__main__':unittest.main()
