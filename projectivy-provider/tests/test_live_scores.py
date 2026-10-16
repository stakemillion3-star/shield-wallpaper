import ast
from pathlib import Path
import unittest

source=Path(__file__).resolve().parents[2] / 'generator.py'
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='nba_live_score')
namespace={}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
live=namespace['nba_live_score']

def event(period=2,detail='6:43 - 2nd',left='35',right='21'):
    return dict(period=period,detail=detail,teams=[('Toronto Raptors',left,'away'),('New York Knicks',right,'home')],
        period_scores={'Toronto Raptors':[20,15],'New York Knicks':[18,3]})

class LiveScoresTests(unittest.TestCase):
    def test_in_quarter_uses_current_scores(self):
        scores,label=live(event())
        self.assertEqual(scores,{'Toronto Raptors':35,'New York Knicks':21})
        self.assertEqual(label,'2Q')
    def test_first_quarter_displays_scores(self):
        self.assertEqual(live(event(1,'5:12 - 1st','12','9'))[1],'1Q')
    def test_fourth_quarter_does_not_hold_third_quarter_score(self):
        scores,label=live(event(4,'0:50 - 4th','120','122'))
        self.assertEqual(scores['Toronto Raptors'],120)
        self.assertEqual(label,'4Q')
    def test_breaks_use_current_totals(self):
        self.assertEqual(live(event(2,'Halftime'))[1],'HALFTIME')
        self.assertEqual(live(event(3,'End of 3rd'))[1],'END 3Q')
    def test_overtime(self):
        self.assertEqual(live(event(5,'2:03 - OT'))[1],'OT')
        self.assertEqual(live(event(6,'2:03 - 2OT'))[1],'2OT')
    def test_missing_scores_are_not_invented(self):
        self.assertIsNone(live(event(left=None))[0])
        self.assertIsNone(live(event(right='-1'))[0])
    def test_zero_score_is_valid(self):
        self.assertEqual(live(event(1,'12:00 - 1st','0','0'))[0]['Toronto Raptors'],0)
    def test_missing_period_can_use_espn_detail(self):
        self.assertEqual(live(event(None,'6:43 - 2nd'))[1],'2Q')

if __name__=='__main__': unittest.main()
