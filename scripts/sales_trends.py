#!/usr/bin/env python3
"""Monthly MoM/YoY ecommerce performance from a daily sales CSV (reconstructed)."""
import argparse
from pathlib import Path
import pandas as pd


def analyze(df):
    if not {'Day', 'Net sales'}.issubset(df.columns):
        raise ValueError('CSV requires Day and Net sales columns')
    d = df.copy()
    d['Day'] = pd.to_datetime(d['Day'], errors='coerce')
    d['Net sales'] = pd.to_numeric(d['Net sales'].astype(str).str.replace(r'[$,]', '',regex=True),errors='coerce')
    if d['Day'].isna().any() or d['Net sales'].isna().any():
        raise ValueError('Unparseable Day or Net sales values')
    for col in ('Gross profit', 'Orders'):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col].astype(str).str.replace(r'[$,]', '',regex=True), errors='coerce')
    cols = ['Net sales'] + [c for c in ('Gross profit','Orders') if c in d]
    daily = d.groupby('Day', as_index=False)[cols].sum()
    monthly = daily.set_index('Day')[cols].resample('MS').sum().reset_index()
    monthly['MoM sales change %'] = monthly['Net sales'].pct_change(fill_method=None)*100
    monthly['YoY sales change %'] = monthly['Net sales'].pct_change(periods=12,fill_method=None)*100
    if 'Orders' in monthly:
        monthly['Average order value'] = monthly['Net sales'].div(monthly['Orders'].replace(0,float('nan')))
    if 'Gross profit' in monthly:
        monthly['Gross margin %'] = monthly['Gross profit'].div(monthly['Net sales'].replace(0,float('nan')))*100
    return daily, monthly

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', type=Path); p.add_argument('--out',type=Path,default=Path('output'))
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    day,month=analyze(pd.read_csv(a.csv))
    day.to_csv(a.out/'sales_daily.csv',index=False)
    month.to_csv(a.out/'sales_monthly.csv',index=False)
    print('Created daily and monthly sales reports in',a.out)
