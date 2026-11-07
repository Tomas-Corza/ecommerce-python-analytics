#!/usr/bin/env python3
"""Campaign spend vs attributed sales; comparisons are descriptive, not causal (reconstructed)."""
import argparse
from pathlib import Path
import pandas as pd


def analyze(spend, sales):
    required_spend={'Campaign','Spend'}; required_sales={'Campaign','Net sales','Orders'}
    if not required_spend.issubset(spend): raise ValueError(f'Spend CSV requires {required_spend}')
    if not required_sales.issubset(sales): raise ValueError(f'Sales CSV requires {required_sales}')
    spend=spend.copy();sales=sales.copy()
    for frame, cols in [(spend,['Spend']),(sales,['Net sales','Orders'])]:
        for col in cols:
            frame[col]=pd.to_numeric(frame[col].astype(str).str.replace(r'[$,]','',regex=True),errors='raise')
    s=spend.groupby('Campaign',as_index=False)['Spend'].sum()
    r=sales.groupby('Campaign',as_index=False)[['Net sales','Orders']].sum()
    out=s.merge(r,on='Campaign',how='outer',validate='one_to_one',indicator='Match status')
    out[['Spend','Net sales','Orders']]=out[['Spend','Net sales','Orders']].fillna(0)
    out['Attributed ROAS']=out['Net sales'].div(out['Spend'].replace(0,float('nan')))
    out['Cost per attributed order']=out['Spend'].div(out['Orders'].replace(0,float('nan')))
    return out.sort_values('Spend',ascending=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('spend_csv',type=Path);p.add_argument('sales_csv',type=Path);p.add_argument('--out',type=Path,default=Path('output/campaign_performance.csv'))
    a=p.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    analyze(pd.read_csv(a.spend_csv),pd.read_csv(a.sales_csv)).to_csv(a.out,index=False)
    print('Created',a.out)
