import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('standings_generator',Path(__file__).resolve().parents[2]/'generator.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class RegularStandingsTests(unittest.TestCase):
    def table(self,kind=2,year=2027):
        return {'children':[{'name':'Eastern Conference','standings':{'seasonType':kind,'season':year,'entries':[{'team':{'displayName':name,'abbreviation':abbr},'stats':[{'name':'wins','displayValue':'0'},{'name':'losses','displayValue':'0'},{'name':'playoffSeed','displayValue':str(i+1)}]} for i,(abbr,name) in enumerate([('TOR','Toronto Raptors')]+[(str(i),'Team '+str(i)) for i in range(14)])]}}]}
    def test_explicit_regular_season_and_zero_records(self):
        with patch.object(g,'get',return_value=self.table()) as fetch:
            rows=g.nba_regular_standings_data(2027)
        self.assertIn('seasontype=2',fetch.call_args.args[0])
        self.assertEqual(len(rows),15)
        self.assertTrue(all(r['wins']=='0' and r['losses']=='0' for r in rows))
    def test_rejects_preseason_and_previous_year(self):
        for data in (self.table(kind=1),self.table(year=2026)):
            with patch.object(g,'get',return_value=data),self.assertRaises(ValueError):
                g.nba_regular_standings_data(2027)
if __name__=='__main__': unittest.main()
