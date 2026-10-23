from datetime import datetime
from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('opener_generator',Path(__file__).resolve().parents[2]/'generator.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class OpenerExpiryTests(unittest.TestCase):
    def test_noon_cutoff_for_both_sports_and_dst_change(self):
        for sport in ('nba','soccer'):
            for month,day,next_day in ((10,16,17),(10,31,1)):
                event=dict(sport=sport,completed=True,date=datetime(2026,month,day,23,30,tzinfo=g.TZ))
                next_month=11 if day==31 else month
                self.assertFalse(g.final_is_expired(event,datetime(2026,next_month,next_day,11,59,tzinfo=g.TZ)))
                self.assertTrue(g.final_is_expired(event,datetime(2026,next_month,next_day,12,0,tzinfo=g.TZ)))
                self.assertFalse(g.final_is_expired(dict(event,completed=False),datetime(2026,next_month,next_day,13,tzinfo=g.TZ)))
    def test_only_first_regular_season_game_is_opener(self):
        def raw(day,kind):
            return dict(id=str(day),date=f'2026-10-{day:02d}T23:30Z',seasonType={'type':kind},status={'type':{'state':'pre','completed':False}},competitions=[{'competitors':[{'team':{'displayName':'Toronto Raptors'},'homeAway':'home'},{'team':{'displayName':'Chicago Bulls'},'homeAway':'away'}]}])
        class Fixed(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,10,18,tzinfo=g.TZ)
        with patch.object(g,'datetime',Fixed),patch.object(g,'get',side_effect=lambda url: {'events':[raw(21,2),raw(23,2)]} if '/schedule?' in url else {'events':[]}):
            last,upcoming,phase=g.raptors()
        self.assertEqual(phase,'REGULAR SEASON')
        self.assertEqual(g.nba_heading(upcoming[0]),'Season Opener')
        self.assertEqual(g.nba_heading(upcoming[1]),'')
        self.assertEqual(g.nba_heading({'season_type':1}),'')
if __name__=='__main__': unittest.main()
