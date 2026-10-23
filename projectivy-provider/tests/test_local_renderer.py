import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from PIL import Image

MODULE=Path(__file__).resolve().parents[1]/'local_renderer.py'
spec=importlib.util.spec_from_file_location('local_renderer_test',MODULE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LocalRendererTests(unittest.TestCase):
    def setUp(self):
        self.original=Path.cwd();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.draws=0;self.score='35';self.period=2;self.clock='6:43';self.time='LIVE • TODAY';self.broken=False
        self.g=types.ModuleType('generator')
        self.g.nba_heading=lambda event:''
        self.g.get=lambda *a,**k:{}
        self.g.remote_image=lambda *a:None
        self.g.standings_data=lambda sport:[]
        self.g.event_time_label=lambda event:self.time
        self.g.nba_live_score=lambda event:(None,f'{self.period}Q')
        self.g.soccer_live_label=lambda event:self.clock
        for name in ('background','draw_centered_panel','draw_event_row','draw_compact_event_panel','draw_standings_panel','place_icon'):
            setattr(self.g,name,lambda *a,**k:None)
        def main(before_render):
            event=dict(sport='nba',phase='PRESEASON',completed=False,state='in',teams=[('Toronto Raptors',self.score,'away'),('New York Knicks','21','home')])
            if not before_render([event],False,None,''):return False
            self.draws+=1
            if self.broken:Path('wallpaper.jpg').write_text('broken')
            else:Image.new('RGB',(32,18),color=(int(self.score),0,0)).save('wallpaper.jpg')
        self.g.main=main
    def tearDown(self):os.chdir(self.original);self.temp.cleanup()
    def run_render(self,gate=None):
        with patch.dict('sys.modules',{'generator':self.g}),patch.object(m.importlib,'reload',return_value=self.g):
            return m.render(str(self.root),gate,'revision-1')
    def test_identical_display_does_not_redraw(self):
        first=self.run_render();second=self.run_render()
        self.assertEqual(first,second);self.assertEqual(self.draws,1)
    def test_new_score_redraws_and_preserves_previous(self):
        first=Path(self.run_render());self.score='36';second=Path(self.run_render())
        self.assertNotEqual(first,second);self.assertTrue(first.exists());self.assertEqual(self.draws,2)
    def test_hidden_clock_changes_do_not_redraw_nba(self):
        self.run_render();self.clock='6:42';self.run_render();self.assertEqual(self.draws,1)
    def test_quarter_changes_redraw(self):
        self.run_render();self.period=3;self.run_render();self.assertEqual(self.draws,2)
    def test_day_label_changes_redraw(self):
        self.run_render();self.time='YESTERDAY • FINAL';self.run_render();self.assertEqual(self.draws,2)
    def test_invalid_output_preserves_last_good_state(self):
        first=Path(self.run_render());data=first.read_bytes();saved=(self.root/'display_state.json').read_bytes()
        self.broken=True;self.score='36'
        with self.assertRaises(Exception):self.run_render()
        self.assertEqual(first.read_bytes(),data);self.assertEqual((self.root/'display_state.json').read_bytes(),saved)
    def test_saved_history_records_day_label_change(self):
        self.time='TOMORROW • 7:00 PM';self.run_render()
        self.time='TODAY • 7:00 PM';self.run_render()
        history=(self.root/'refresh-history.jsonl').read_text()
        self.assertIn('TOMORROW',history);self.assertIn('TODAY',history)
        self.assertEqual(self.draws,2)
    def test_failure_is_saved_without_losing_last_good_image(self):
        first=Path(self.run_render());self.broken=True;self.score='36'
        with self.assertRaises(Exception):self.run_render()
        self.assertTrue(first.exists())
        self.assertIn('"event": "failed"',(self.root/'refresh-history.jsonl').read_text())
    def test_history_is_bounded(self):
        log=self.root/'refresh-history.jsonl';log.write_text(('x'*1000+'\n')*100)
        m.diagnostic(self.root,'test')
        m.diagnostic(self.root,'test')
        self.assertLess(log.stat().st_size,102000)
    def test_background_gate_prevents_work(self):
        gate=types.SimpleNamespace(isAllowed=lambda:False)
        with self.assertRaises(m.Paused):self.run_render(gate)
        self.assertEqual(self.draws,0)
    def test_leaving_home_before_drawing_does_not_publish(self):
        calls=[True,False]
        gate=types.SimpleNamespace(isAllowed=lambda:calls.pop(0) if calls else False)
        self.assertEqual(self.run_render(gate),'');self.assertEqual(self.draws,0)
        self.assertFalse((self.root/'display_state.json').exists())

if __name__=='__main__':unittest.main()
