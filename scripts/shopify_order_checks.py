#!/usr/bin/env python3
"""Validate Ecommerce Shopify order exports and produce audit-safe reconciliation outputs."""
from pathlib import Path
import argparse
import pandas as pd

P = argparse.ArgumentParser()
P.add_argument('folder', nargs='?', default='.')
a = P.parse_args()
root = Path(a.folder).expanduser().resolve()
inputs = {'orders':'Shopify_Order_Level.csv','utm':'Shopify_Order_Level_Attribution.csv','lines':'Shopify_Order_Line_Profitability.csv'}
dfs = {}
for kind, filename in inputs.items():
    path=root/filename
    if not path.exists():
        raise SystemExit(f'Missing {filename} in {root}')
    df=pd.read_csv(path, encoding='utf-8-sig', dtype={'Order ID':'string'}, low_memory=False)
    df.columns=df.columns.str.strip()
    if 'Order ID' not in df.columns:
        raise SystemExit(f'{filename}: Order ID column missing. Found {list(df.columns)}')
    df['Order ID']=df['Order ID'].astype('string').str.strip()
    dfs[kind]=df
    print(f'{filename}: {len(df):,} rows, {df["Order ID"].nunique(dropna=True):,} distinct IDs')
orders,utm,lines=dfs['orders'],dfs['utm'],dfs['lines']
required={'orders':['Net sales','Gross profit','Cost of goods sold','Orders'], 'utm':['Net sales','Gross profit','Order UTM source','Order UTM medium','Order UTM campaign'], 'lines':['Net sales','Gross profit','Cost of goods sold']}
for kind, fields in required.items():
    absent=[c for c in fields if c not in dfs[kind].columns]
    if absent: raise SystemExit(f'{inputs[kind]} missing fields: {absent}')
for label, df in [('orders',orders),('utm',utm),('lines',lines)]:
    print(f'{label}: blank order IDs {df["Order ID"].isna().sum():,}; duplicated order ID rows {df["Order ID"].duplicated().sum():,}')
if orders['Order ID'].isna().any() or orders['Order ID'].duplicated().any():
    raise SystemExit('Order master contains blank or duplicated order IDs; stopped to avoid multiplying financial data.')
for df in (orders,utm,lines):
    for name in ('Net sales','Gross profit','Cost of goods sold','Orders'):
        if name in df.columns:
            df[name]=pd.to_numeric(df[name].astype('string').str.replace(r'[$,%\s,]','',regex=True),errors='coerce')
master_ids=set(orders['Order ID'].dropna())
checks=[]
for name,df in [('Attribution',utm),('Line items',lines)]:
    ids=set(df['Order ID'].dropna())
    checks.append({'dataset':name,'rows':len(df),'distinct_order_ids':len(ids),'missing_from_master':len(ids-master_ids),'master_ids_not_in_dataset':len(master_ids-ids)})
    print(f'{name}: extra IDs {len(ids-master_ids):,}, master IDs not covered {len(master_ids-ids):,}')
# Distinct UTM tuples are not necessarily unique by order. Do not join blindly.
utm_group_counts=utm.groupby('Order ID',dropna=False).size()
print(f'Attribution IDs with multiple rows: {(utm_group_counts>1).sum():,}')
# Aggregate line items to order grain, compare sales and gross profit.
line_totals=lines.groupby('Order ID',dropna=False)[['Net sales','Gross profit','Cost of goods sold']].sum(min_count=1).reset_index()
comparison=orders[['Order ID','Order name','Net sales','Gross profit','Cost of goods sold']].merge(line_totals,on='Order ID',how='left',suffixes=('_order','_lines'),validate='one_to_one',indicator=True)
for field in ('Net sales','Gross profit','Cost of goods sold'):
    comparison[f'{field} difference']=comparison[f'{field}_order']-comparison[f'{field}_lines']
comparison['Net sales mismatch over $0.02']=comparison['Net sales difference'].abs().gt(.02)
comparison['Profit mismatch over $0.02']=comparison['Gross profit difference'].abs().gt(.02)
print(f'Order IDs with no line records: {(comparison["_merge"]=="left_only").sum():,}')
print(f'Net sales mismatches > $0.02: {comparison["Net sales mismatch over $0.02"].sum():,}')
print(f'Gross profit mismatches > $0.02: {comparison["Profit mismatch over $0.02"].sum():,}')
# UTM report may have multiple attribution combinations per order. Keep separate; never sum repeated order values as distinct sales.
utm_unique=utm.drop_duplicates(subset=['Order ID']).copy()
raw_dup_count=int((utm_group_counts>1).sum())
joined=orders.merge(utm_unique[['Order ID','Order UTM source','Order UTM medium','Order UTM campaign']],on='Order ID',how='left',validate='one_to_one')
fields=['Order UTM source','Order UTM medium','Order UTM campaign']
for f in fields: joined[f]=joined[f].fillna('').astype(str)
# Conservative tagging, NOT a unique attribution model.
joined['Email UTM indicator']=joined['Order UTM medium'].str.contains(r'(^|[^a-z])email([^a-z]|$)',case=False,regex=True) | joined['Order UTM source'].str.contains('klaviyo',case=False,regex=False)
# Where multiple UTM rows exist per order, flag such records as ambiguous rather than treating arbitrary first as definitive.
ambiguous_ids=set(utm_group_counts[utm_group_counts>1].index)
joined['UTM multiple rows']=joined['Order ID'].isin(ambiguous_ids)
email=joined[joined['Email UTM indicator'] & ~joined['UTM multiple rows']]
summary=pd.DataFrame([
    {'metric':'Shopify order report rows','value':len(orders)},
    {'metric':'Distinct Shopify order IDs','value':orders['Order ID'].nunique()},
    {'metric':'Sum Shopify order report net sales','value':orders['Net sales'].sum(min_count=1)},
    {'metric':'Sum Shopify order report gross profit','value':orders['Gross profit'].sum(min_count=1)},
    {'metric':'Sum Shopify order report COGS','value':orders['Cost of goods sold'].sum(min_count=1)},
    {'metric':'Order IDs with multiple attribution rows','value':raw_dup_count},
    {'metric':'Email-tagged unambiguous order IDs','value':len(email)},
    {'metric':'Email-tagged unambiguous net sales (UTM indicator, not causal)','value':email['Net sales'].sum(min_count=1)},
    {'metric':'Email-tagged unambiguous gross profit (UTM indicator, not causal)','value':email['Gross profit'].sum(min_count=1)},
    {'metric':'Order vs line net sales mismatches above $0.02','value':comparison['Net sales mismatch over $0.02'].sum()},
    {'metric':'Order vs line gross profit mismatches above $0.02','value':comparison['Profit mismatch over $0.02'].sum()},
])
out=root/'Order_Reconciliation_Checks.xlsx'
with pd.ExcelWriter(out, engine='openpyxl') as writer:
    summary.to_excel(writer,'Summary',index=False)
    pd.DataFrame(checks).to_excel(writer,'ID_Coverage',index=False)
    comparison.to_excel(writer,'Order_Line_Checks',index=False)
    joined.to_excel(writer,'Orders_With_UTM',index=False)
    if raw_dup_count:
        utm[utm['Order ID'].isin(ambiguous_ids)].to_excel(writer,'Multi_UTM_Orders',index=False)
print(f'Created: {out.name}')
print('Do not equate UTM indicators with Klaviyo conversion-event matches or incremental profit.')
