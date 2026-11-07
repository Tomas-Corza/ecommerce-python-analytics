#!/usr/bin/env python3
"""Ecommerce Shopify order-level reconciliation, configurable date range.
Run: python3 scripts/shopify_profit_reconciliation.py /path/to/exports
Requires pandas, openpyxl. Does NOT assert Klaviyo conversion-level matching.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.cwd()
START = pd.Timestamp(__import__("os").environ.get("REPORT_START", "2025-01-01"))
END = pd.Timestamp(__import__("os").environ.get("REPORT_END_EXCLUSIVE", "2026-01-01"))
FILES = {
    'orders': 'Shopify_Order_Level.csv',
    'attribution': 'Shopify_Order_Level_Attribution.csv',
    'lines': 'Shopify_Order_Line_Profitability.csv',
}
required = {
    'orders': ['Order ID', 'Order name', 'Net sales', 'Cost of goods sold', 'Gross profit'],
    'attribution': ['Order ID', 'Order name', 'Net sales', 'Order UTM source', 'Order UTM medium', 'Order UTM campaign', 'Order UTM content'],
    'lines': ['Order ID', 'Order name', 'Product title', 'Net sales', 'Cost of goods sold', 'Gross profit'],
}
frames = {}
for label, filename in FILES.items():
    path = ROOT / filename
    if not path.exists():
        sys.exit(f'Missing {filename}. Place it in {ROOT}')
    df = pd.read_csv(path, encoding='utf-8-sig', dtype=str, low_memory=False)
    df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
    absent = [c for c in required[label] if c not in df.columns]
    if absent:
        sys.exit(f'{filename}: missing columns: {absent}; found: {list(df.columns)}')
    df['Order ID'] = df['Order ID'].fillna('').str.strip().str.replace(r'\.0$', '', regex=True)
    df['Order name'] = df['Order name'].fillna('').str.strip()
    frames[label] = df
    print(f'{filename}: {len(df):,} rows, {df["Order ID"].nunique():,} distinct Order IDs')

def numeric(s):
    return pd.to_numeric(s.fillna('').astype(str).str.replace(r'[$,%\s,]', '', regex=True).replace('', np.nan), errors='coerce')

orders, attribution, lines = (frames[k] for k in ('orders','attribution','lines'))
for df in (orders, attribution, lines):
    for col in ('Orders','Net sales','Gross sales','Total sales','Discounts','Returns','Sales reversals','Cost of goods sold','Gross profit','Quantity ordered','Net items sold'):
        if col in df:
            df[col] = numeric(df[col])

# Never silently collapse duplicate order IDs: output examples and use sums only when appropriate.
dup_orders = orders[orders['Order ID'].duplicated(False) | orders['Order ID'].eq('')].copy()
dup_attr = attribution[attribution['Order ID'].duplicated(False) | attribution['Order ID'].eq('')].copy()
if len(dup_orders) or len(dup_attr):
    print('WARNING: duplicate/blank Order IDs in order or attribution file. Review Duplicate_IDs before interpreting merged metrics.')

# Use a unique per-order attribution classification without multiplying rows.
utm_cols = ['Order UTM source','Order UTM medium','Order UTM campaign','Order UTM content']
for col in utm_cols:
    attribution[col] = attribution[col].fillna('').astype(str).str.strip()
attr_lookup = attribution.groupby('Order ID', as_index=False).agg({
    'Order name':'first',
    **{c: lambda values: ' | '.join(sorted(set(v for v in values if v)))[:500] for c in utm_cols},
    'Net sales': 'sum',
})
attr_lookup.rename(columns={'Order name':'Attribution order name','Net sales':'Attribution net sales'}, inplace=True)

# Classify explicit email signal; do not infer email from campaign names alone.
src = attr_lookup['Order UTM source'].str.lower()
med = attr_lookup['Order UTM medium'].str.lower()
attr_lookup['Email UTM signal'] = med.str.contains(r'(^|\W)(email|e-mail)(\W|$)',regex=True, na=False) | src.str.contains('klaviyo',regex=False,na=False)
attr_lookup['Klaviyo source signal'] = src.str.contains('klaviyo',regex=False,na=False)

# Shopify order-level is one row per ID only if duplicate test passes; preserve duplicates visibly.
order_roll = orders.groupby('Order ID', as_index=False).agg({
    'Order name':'first', 'Net sales':'sum', 'Cost of goods sold':'sum','Gross profit':'sum',
    **({'Gross sales':'sum'} if 'Gross sales' in orders else {}),
    **({'Discounts':'sum'} if 'Discounts' in orders else {}),
    **({'Returns':'sum'} if 'Returns' in orders else {}),
})
order_roll.rename(columns={'Net sales':'Order net sales','Cost of goods sold':'Order COGS','Gross profit':'Order gross profit'}, inplace=True)
line_roll = lines.groupby('Order ID',as_index=False)[['Net sales','Cost of goods sold','Gross profit']].sum(min_count=1)
line_roll.rename(columns={'Net sales':'Line net sales','Cost of goods sold':'Line COGS','Gross profit':'Line gross profit'}, inplace=True)
joined = order_roll.merge(attr_lookup,on='Order ID',how='outer',indicator='Order vs attribution',validate='one_to_one')
joined = joined.merge(line_roll,on='Order ID',how='outer',indicator='Order/attr vs lines',validate='one_to_one')
for col in ('Line net sales','Line COGS','Line gross profit','Attribution net sales'):
    joined[f'Diff order minus {col}'] = joined['Order net sales' if 'net sales' in col else 'Order COGS' if 'COGS' in col else 'Order gross profit'] - joined[col]
joined['Order ID'] = joined['Order ID'].astype(str)
joined['Email UTM signal'] = joined['Email UTM signal'].fillna(False)
joined['Klaviyo source signal'] = joined['Klaviyo source signal'].fillna(False)

email = joined[joined['Email UTM signal'] & joined['Order net sales'].notna()].copy()
non_email = joined[(~joined['Email UTM signal']) & joined['Order net sales'].notna()].copy()

# Import Shopify reported monthly baseline only when schema has monthly identifier.
monthly_path = ROOT / 'Shopify_Monthly_Profitability.csv'
monthly = pd.DataFrame()
if monthly_path.exists():
    monthly = pd.read_csv(monthly_path,encoding='utf-8-sig')

summary_data = [
    ('Reporting start',str(START.date())), ('Reporting end (exclusive)',str(END.date())),
    ('Order source rows',len(orders)), ('Distinct order IDs',orders['Order ID'].nunique()),
    ('Order duplicates / blank IDs',len(dup_orders)),
    ('Attribution rows',len(attribution)), ('Attribution duplicates / blank IDs',len(dup_attr)),
    ('Line-item rows',len(lines)),
    ('Order-level net sales',round(orders['Net sales'].sum(),2)),
    ('Order-level COGS',round(orders['Cost of goods sold'].sum(),2)),
    ('Order-level gross profit',round(orders['Gross profit'].sum(),2)),
    ('Line-level net sales',round(lines['Net sales'].sum(),2)),
    ('Line-level COGS',round(lines['Cost of goods sold'].sum(),2)),
    ('Line-level gross profit',round(lines['Gross profit'].sum(),2)),
    ('Attribution export net sales',round(attribution['Net sales'].sum(),2)),
    ('Email-UTM-associated unique order IDs',email['Order ID'].nunique()),
    ('Email-UTM-associated order net sales',round(email['Order net sales'].sum(),2)),
    ('Email-UTM-associated order gross profit',round(email['Order gross profit'].sum(),2)),
    ('Email orders with missing COGS',int(email['Order COGS'].isna().sum())),
    ('Order IDs absent from attribution',int((joined['Order vs attribution']=='left_only').sum())),
    ('Attribution IDs absent from orders',int((joined['Order vs attribution']=='right_only').sum())),
    ('Order/line net sales mismatch > $0.02',int((joined['Diff order minus Line net sales'].abs()>0.02).sum())),
]
summary = pd.DataFrame(summary_data,columns=['Measure','Value'])
quality = pd.DataFrame([
    {'Check':'Duplicate order IDs', 'Result':'REVIEW' if len(dup_orders) else 'PASS', 'Detail':'If duplicates are expected, reconcile grain before interpreting sums'},
    {'Check':'Duplicate attribution IDs','Result':'REVIEW' if len(dup_attr) else 'PASS','Detail':'Multiple UTM rows per order may be valid; verify source grain'},
    {'Check':'Missing line matches','Result':'REVIEW' if (joined['Order/attr vs lines']!='both').any() else 'PASS','Detail':'Inspect Order_Reconciliation indicator'},
    {'Check':'Order-line sales match','Result':'REVIEW' if (joined['Diff order minus Line net sales'].abs()>0.02).any() else 'PASS','Detail':'Shopify order vs line scope may differ for shipping/taxes/adjustments'},
    {'Check':'Klaviyo event matching','Result':'NOT POSSIBLE','Detail':'Aggregate Klaviyo exports contain no per-conversion Shopify order ID'},
    {'Check':'Historical COGS coverage','Result':'REVIEW','Detail':'Shopify report COGS can be missing and may not cover fees, freight or refunds'},
    {'Check':'Sales-event reporting period','Result':'CAUTION','Detail':'Sales reports may include refunds tied to orders created outside period'},
])

out = ROOT / 'Shopify_Order_Reconciliation.xlsx'
with pd.ExcelWriter(out,engine='openpyxl') as writer:
    for name,frame in [
        ('Executive_Checks',summary), ('Data_Quality',quality),('Order_Reconciliation',joined),
        ('Email_UTM_Orders',email),('Other_Orders',non_email),('Duplicate_Order_IDs',dup_orders),
        ('Duplicate_Attribution_IDs',dup_attr),('Shopify_Monthly_Source',monthly),
    ]:
        if name == 'Shopify_Monthly_Source' and frame.empty: continue
        frame.to_excel(writer,sheet_name=name,index=False)
        ws = writer.sheets[name]
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        from openpyxl.styles import Font, PatternFill
        for cell in ws[1]:
            cell.font=Font(bold=True,color='FFFFFF')
            cell.fill=PatternFill('solid',fgColor='16324A')
        for col in ws.columns:
            letter = col[0].column_letter
            lengths = [len(str(c.value or '')) for c in list(col)[:150]]
            ws.column_dimensions[letter].width = min(45,max(13,max(lengths,default=13)+2))

print(f'Created: {out.name}')
print(f'Order/line discrepancies > $0.02: {summary_data[-1][1]:,}')
print('NOTE: Email UTM signal is not a verified Klaviyo conversion-to-order match.')
