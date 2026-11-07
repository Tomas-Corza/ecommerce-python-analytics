"""Run with python -m unittest discover -s tests."""
import unittest
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sales_trends import analyze as sales
from campaign_performance import analyze as campaigns
from inventory_history import analyze as inventory

ROOT=Path(__file__).resolve().parents[1]/'examples'
class SmokeTest(unittest.TestCase):
    def test_sales(self):
        daily,monthly=sales(pd.read_csv(ROOT/'daily_sales.csv'))
        self.assertEqual(len(monthly),2)
        self.assertAlmostEqual(monthly.iloc[0]['Net sales'],1150)
    def test_campaigns(self):
        out=campaigns(pd.read_csv(ROOT/'campaign_spend.csv'),pd.read_csv(ROOT/'campaign_sales.csv'))
        self.assertEqual(len(out),2)
        self.assertAlmostEqual(out.loc[out.Campaign.eq('Search - Generic'),'Attributed ROAS'].iloc[0],1100/300)
    def test_inventory(self):
        out=inventory(pd.read_csv(ROOT/'inventory_snapshots.csv'),pd.read_csv(ROOT/'variant_sales.csv'))
        self.assertTrue(bool(out.loc[out['Variant SKU'].eq('SKU-101'),'No stock observed'].iloc[0]))
if __name__=='__main__':unittest.main()
