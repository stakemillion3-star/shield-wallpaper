from datetime import date, datetime
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image

path=Path(__file__).resolve().parents[2] / 'generator.py'
spec=importlib.util.spec_from_file_location('panel_generator',path)
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class PanelFormattingTests(unittest.TestCase):
    def setUp(self): g.DISPLAY_DATE=date(2026,10,15)
    def fmt(self,value): return g.fmt_date(datetime.fromisoformat(value.replace('Z','+00:00')))
    def test_pistons_tipoff(self):
        self.assertEqual(self.fmt('2026-10-16T23:00Z'),'TOMORROW • 7:00 PM')
    def test_noon_and_midnight(self):
        self.assertEqual(self.fmt('2026-10-16T04:00Z'),'TOMORROW • 12:00 AM')
        self.assertEqual(self.fmt('2026-10-16T16:00Z'),'TOMORROW • 12:00 PM')
    def test_winter_eastern_time(self):
        g.DISPLAY_DATE=date(2027,1,13)
        self.assertEqual(self.fmt('2027-01-15T00:00Z'),'TOMORROW • 7:00 PM')
    def texts(self,second_sport):
        events=[dict(date=datetime(2026,10,15,19,tzinfo=g.TZ),day_offset=0,completed=True,state='post',sport='nba',phase='PRESEASON',teams=[('Toronto Raptors','120','away'),('New York Knicks','122','home')]),
                dict(date=datetime(2026,10,16,19,tzinfo=g.TZ),day_offset=1,completed=False,state='pre',sport=second_sport,phase='PRESEASON' if second_sport=='nba' else '',teams=[('Toronto Raptors',None,'away'),('Detroit Pistons',None,'home')])]
        texts=[]
        with patch.object(g,'centered_text',side_effect=lambda d,t,*args,**kwargs:texts.append(t)),patch.object(g,'place_icon',return_value=None):
            g.draw_centered_panel(Image.new('RGBA',(g.W,g.H)),events,False,'')
        return texts
    def test_same_league_heading_only_once(self):
        texts=self.texts('nba')
        self.assertEqual(texts.count('PRESEASON'),1)
        self.assertIn('TOMORROW • 7:00 PM',texts)
    def test_mixed_leagues_keep_lower_heading(self):
        texts=self.texts('soccer')
        self.assertIn('PRESEASON',texts)
        self.assertIn('NATIONS LEAGUE',texts)

    def test_regular_season_standings_panel_renders(self):
        rows=[dict(abbr='TOR',name='Toronto Raptors',rank='7',wins='3',losses='2',pct='.600',gb='1.0')]
        with patch.object(g,'standings_data',return_value=rows),patch.object(g,'team_icon',return_value=None):
            result=g.draw_standings_panel(Image.new('RGBA',(g.W,g.H)),500,1200,2500,450,'',sport='nba')
        self.assertEqual(result.size,(g.W,g.H))
    def test_bosnia_standings_panel_renders(self):
        rows=[('1','Bosnia and Herzegovina','4','2','1','1','+2','7')]
        with patch.object(g,'standings_data',return_value=rows),patch.object(g,'team_icon',return_value=None):
            result=g.draw_standings_panel(Image.new('RGBA',(g.W,g.H)),500,1200,2500,450,'NATIONS LEAGUE',sport='soccer')
        self.assertEqual(result.size,(g.W,g.H))

if __name__=='__main__': unittest.main()
