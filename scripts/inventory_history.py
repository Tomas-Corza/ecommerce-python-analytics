#!/usr/bin/env python3
"""Identify historically selling variants with no observed stock (reconstructed)."""
import argparse
from pathlib import Path
import pandas as pd


def analyze(history, sales):
    # History must contain periodic snapshots; missing snapshots do not prove no stock.
    for label,frame,cols in [('history',history,{'Variant SKU','Snapshot date','Available quantity'}),('sales',sales,{'Variant SKU','Historical net sales'})]:
        if not cols.issubset(frame): raise ValueError(f'{label} requires {cols}')
    h=history.copy();s=sales.copy()
    h['Snapshot date']=pd.to_datetime(h['Snapshot date'],errors='raise')
    h['Available quantity']=pd.to_numeric(h['Available quantity'],errors='raise')
    s['Historical net sales']=pd.to_numeric(s['Historical net sales'],errors='raise')
    stock=h.groupby('Variant SKU',as_index=False).agg(observed_snapshots=('Snapshot date','nunique'),max_observed_qty=('Available quantity','max'))
    revenue=s.groupby('Variant SKU',as_index=False)['Historical net sales'].sum()
    out=revenue.merge(stock,how='left',on='Variant SKU',validate='one_to_one')
    out['No stock observed']=out['observed_snapshots'].gt(0)&out['max_observed_qty'].le(0)
    out['Coverage warning']=out['observed_snapshots'].isna()
    return out.sort_values('Historical net sales',ascending=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshots_csv',type=Path);p.add_argument('sales_csv',type=Path);p.add_argument('--out',type=Path,default=Path('output/inventory_history.csv'))
    a=p.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    analyze(pd.read_csv(a.snapshots_csv),pd.read_csv(a.sales_csv)).to_csv(a.out,index=False)
    print('Created',a.out)
