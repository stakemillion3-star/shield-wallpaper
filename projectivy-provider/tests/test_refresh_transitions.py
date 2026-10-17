from datetime import datetime as Real
from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('transition_generator',root/'generator.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
spec=importlib.util.spec_from_file_location('transition_renderer',root/'projectivy-provider/local_renderer.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Fixed(Real):
    hour_value=11
    minute_value=59
    @classmethod
    def now(cls,tz=None):
        value=cls(2026,10,16,cls.hour_value,cls.minute_value,tzinfo=g.TZ)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)

class RefreshTransitionsTests(unittest.TestCase):
    def setUp(self):
        g.DISPLAY_DATE=None
        self.yesterday=dict(date=Real(2026,10,15,19,30,tzinfo=g.TZ),completed=True,state='post',detail='Final',teams=[('Toronto Raptors','120','away'),('New York Knicks','122','home')])
        self.today=dict(date=Real(2026,10,16,19,tzinfo=g.TZ),completed=False,state='pre',detail='Scheduled',teams=[('Toronto Raptors',None,'away'),('Detroit Pistons',None,'home')])
    def state_at(self,hour,minute,live=None):
        Fixed.hour_value=hour;Fixed.minute_value=minute
        captured=[]
        def capture(events,show,sport,label):
            captured.append(r.display_state(g,events,show,sport,label,'same-source'))
            return False
        with patch.object(g,'datetime',Fixed),patch.object(g,'bosnia',return_value=(None,[],'')),patch.object(g,'raptors',return_value=(live if live else self.yesterday,[] if live else [self.today],'PRESEASON')):
            g.main(before_render=capture)
        return captured[0]
    def test_noon_removes_old_final_and_invalidates_display_signature(self):
        before=self.state_at(11,59);after=self.state_at(12,0)
        self.assertEqual(len(before['cards']),2);self.assertEqual(len(after['cards']),1)
        self.assertFalse(after['cards'][0]['completed']);self.assertNotEqual(before,after)
    def test_live_changes_reach_display_state(self):
        live=dict(self.today,state='in',detail='6:43 - 2nd',period=2,teams=[('Toronto Raptors','35','away'),('Detroit Pistons','21','home')])
        a=self.state_at(20,0,live)
        live=dict(live,teams=[('Toronto Raptors','37','away'),('Detroit Pistons','21','home')])
        b=self.state_at(20,1,live)
        self.assertEqual(a['cards'][0]['scores'],['35','21'])
        self.assertEqual(a['cards'][0]['live_label'],'2Q');self.assertNotEqual(a,b)
    def test_final_replaces_live_without_reintroducing_yesterdays_result(self):
        final=dict(self.today,completed=True,state='post',detail='Final',teams=[('Toronto Raptors','125','away'),('Detroit Pistons','120','home')])
        state=self.state_at(22,0,final)
        self.assertEqual(len(state['cards']),1);self.assertTrue(state['cards'][0]['completed'])

if __name__=='__main__':unittest.main()
