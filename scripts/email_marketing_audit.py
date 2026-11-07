#!/usr/bin/env python3
"""Ecommerce annual email audit from manual Shopify/Klaviyo CSV exports.
Usage: python3 scripts/email_marketing_audit.py /path/to/exports
Requires: pandas, openpyxl. Never edits input CSVs or the original audit workbook.
"""
from pathlib import Path
import sys, csv, re
import pandas as pd

folder = Path(sys.argv[1]).expanduser() if len(sys.argv)>1 else Path('.')
out = folder/'Email_Marketing_Audit.xlsx'
START = pd.Timestamp(__import__('os').environ.get('REPORT_START', '2025-01-01'))
END = pd.Timestamp(__import__('os').environ.get('REPORT_END', '2025-12-31'))
notes=[]; tables={}

def load_csv(path, markers):
    if not path.exists(): return None
    # Find actual header: Klaviyo sometimes prepends metadata lines.
    with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
        lines=[]
        for idx,line in enumerate(f):
            if idx>=25: break
            columns=next(csv.reader([line])) if line.strip() else []
            clean={c.strip().casefold() for c in columns}
            if all(m.casefold() in clean for m in markers):
                return pd.read_csv(path, skiprows=idx, dtype=str, low_memory=False, encoding='utf-8-sig')
    notes.append(('READ ERROR',path.name,'Cannot locate expected columns: '+', '.join(markers)))
    return None

def number(df, name):
    if name not in df.columns: return pd.Series(0.,index=df.index)
    s=df[name].astype('string').str.replace(r'[$,%\s,]','',regex=True)
    return pd.to_numeric(s,errors='coerce').fillna(0)

def datetime_col(df,col):
    if col not in df.columns:
        return pd.Series(pd.NaT,index=df.index,dtype='datetime64[ns]')
    # Parse each timestamp independently: Klaviyo may mix PST/PDT offsets in
    # the same export, which pandas 3 rejects as a single datetime array.
    # Keep naive timestamps at their exported wall-clock hour; convert only
    # timezone-aware timestamps into Los Angeles time.
    raw=df[col].astype('string').str.strip()
    aware_count=0
    invalid_count=0
    def parse_one(value):
        nonlocal aware_count, invalid_count
        if pd.isna(value) or not str(value).strip():
            return pd.NaT
        try:
            timestamp=pd.Timestamp(str(value))
            if timestamp.tzinfo is not None:
                aware_count+=1
                timestamp=timestamp.tz_convert('America/Los_Angeles').tz_localize(None)
            return timestamp
        except (ValueError, TypeError, OverflowError):
            invalid_count+=1
            return pd.NaT
    parsed=raw.map(parse_one)
    parsed=pd.to_datetime(parsed,errors='coerce')
    if aware_count:
        notes.append(('TIMEZONE',col,f'{aware_count:,} offset-aware values converted to America/Los_Angeles; confirm account timezone'))
    if invalid_count:
        notes.append(('QUALITY',col,f'{invalid_count:,} invalid timestamp values could not be parsed'))
    return parsed

def ranking(df, by, kind='campaign'):
    g=df.groupby(by,dropna=False).agg(records=('revenue','size'),revenue=('revenue','sum'),delivered=('delivered','sum'),orders=('orders','sum'),unsubscribes=('unsubscribes',lambda v: v.sum(min_count=1))).reset_index()
    d=g.delivered.mask(g.delivered.eq(0))
    g['revenue_per_1000_delivered']=g.revenue/d*1000
    g['orders_per_1000_delivered']=g.orders/d*1000
    g['unsub_rate']=g.unsubscribes/d
    return g.sort_values('revenue_per_1000_delivered',ascending=False)

# Shopify baseline
s=load_csv(folder/'Shopify_Daily_Profitability.csv',['Day','Net sales'])
if s is not None:
    s['date']=pd.to_datetime(s['Day'],errors='coerce')
    s=s[s.date.between(START,END)].copy()
    s['revenue']=number(s,'Net sales'); s['weekday']=s.date.dt.day_name()
    s['gross_profit']=number(s,'Gross profit')
    tables['Shopify_Weekdays']=s.groupby('weekday').agg(days=('date','nunique'),revenue=('revenue','sum'),gross_profit=('gross_profit','sum'),average_daily_sales=('revenue','mean')).reset_index().sort_values('average_daily_sales',ascending=False)
    weekends=s[s.date.dt.weekday>=5].copy()
    weekends['weekend_start']=weekends.date-pd.to_timedelta(weekends.date.dt.weekday-5,unit='D')
    tables['Shopify_Weekends']=weekends.groupby('weekend_start').agg(days=('date','nunique'),revenue=('revenue','sum'),gross_profit=('gross_profit','sum')).reset_index().sort_values('revenue',ascending=False)
    tables['Shopify_Daily']=s[['date','weekday','revenue','gross_profit']]
else:notes.append(('MISSING','Shopify_Daily_Profitability.csv','Storewide baseline unavailable'))

# Flow detail from 180-day exports, not a synthetic annual summary.
part_files=sorted(folder.glob('Klaviyo_Flows_Part*.csv'))
if not part_files and (folder/'Klaviyo_Flows_Annual.csv').exists():
    part_files=[folder/'Klaviyo_Flows_Annual.csv']
frames=[]
for path in part_files:
    f=load_csv(path,['Day','Flow ID','Flow Message ID','Revenue','Delivered'])
    if f is None:continue
    f['source_file']=path.name
    f['date']=pd.to_datetime(f['Day'],errors='coerce')
    notes.append(('SOURCE',path.name,f'{len(f):,} rows; dates {f.date.min()} to {f.date.max()}'))
    frames.append(f)
if frames:
    f=pd.concat(frames,ignore_index=True)
    invalid=f.date.isna().sum()
    if invalid: notes.append(('QUALITY','Flow dates',f'{invalid:,} rows have unparseable dates; excluded'))
    outperiod=(~f.date.between(START,END)).sum()
    if outperiod:notes.append(('QUALITY','Flow date coverage',f'{outperiod:,} records outside selected period; excluded'))
    f=f[f.date.between(START,END)].copy()
    # Remove only exact duplicates of every original data field, excluding source file.
    rawcols=[c for c in f.columns if c not in ['source_file','date']]
    duplicate=f.duplicated(subset=rawcols,keep='first')
    if duplicate.any():
        notes.append(('WARNING','Exact repeated flow rows',f'{int(duplicate.sum()):,} identical records detected across/within exports; NOT automatically dropped (could be valid)'))
    # IMPORTANT: A/B variants are distinct sends, but sum only if mutually exclusive delivery segments.
    f=f[f['Flow Message Channel'].astype(str).str.contains('email',case=False,na=False)].copy()
    f['revenue']=number(f,'Revenue');f['delivered']=number(f,'Delivered');f['orders']=number(f,'Placed Order')
    f['unsubscribes']=float('nan') # only unsubscribe rate provided; do not invent counts
    f['month']=f.date.dt.to_period('M').astype(str)
    f['weekday']=f.date.dt.day_name()
    tables['Flow_By_Name']=ranking(f,['Flow ID','Flow Name'])
    tables['Flow_By_Message']=ranking(f,['Flow ID','Flow Name','Flow Message ID','Flow Message Name','Variant Name'])
    tables['Flow_By_Month']=ranking(f,['month'])
    tables['Flow_By_Weekday']=ranking(f,['weekday'])
    tables['Flow_Daily']=ranking(f,['date'])
    # Raw rows can be inspected from source CSV; do not inflate output to 80k+ rows.
    notes.append(('INTERPRETATION','Flows','Day is a reporting day, not the send hour; weekday analysis does NOT establish optimal send day'))
    notes.append(('CAUTION','Flows','A/B and multi-level reports may overlap; validate source grain and totals before declaring authoritative revenue'))
    notes.append(('LIMITATION','Flow unsubscribes','Flow export has Unsub Rate but no count. Counts and weighted rates intentionally left blank'))
else: notes.append(('MISSING','Flow exports','No readable flow CSVs found'))

# Campaigns: actual export headers supplied by user.
c=load_csv(folder/'Klaviyo_Campaigns_Annual.csv',['Campaign ID','Message send date time','Conversion value','Total deliveries'])
if c is not None:
    if 'Send channel' in c.columns:
        c=c[c['Send channel'].astype(str).str.contains('email',case=False,na=False)].copy()
    c['send_time']=datetime_col(c,'Message send date time')
    c['date']=c.send_time.dt.normalize()
    # Export timezone is unknown. Send hour should not be treated as local until confirmed.
    c=c[c.date.between(START,END)].copy()
    c['revenue']=number(c,'Conversion value');c['delivered']=number(c,'Total deliveries')
    c['orders']=number(c,'Count of unique conversions')
    c['unsubscribes']=number(c,'Unique unsubscribes')
    c['weekday']=c.send_time.dt.day_name()
    c['hour_export_timezone']=c.send_time.dt.hour
    c['month']=c.send_time.dt.to_period('M').astype(str)
    tables['Campaign_By_Name']=ranking(c,['Campaign ID','Campaign name'])
    tables['Campaign_By_Month']=ranking(c,['month'])
    tables['Campaign_Send_Day']=ranking(c,['weekday'])
    tables['Campaign_Send_Hour']=ranking(c,['hour_export_timezone'])
    tables['Campaign_Day_Hour']=ranking(c,['weekday','hour_export_timezone'])
    tables['Campaign_Raw_Check']=c[['Campaign ID','Campaign name','Message send date time','revenue','delivered','orders','unsubscribes']].head(5000)
    notes.append(('CAUTION','Campaign hours','Confirm the exported send-time timezone. Naive timestamps retain the CSV clock hour; timezone-aware timestamps convert to America/Los_Angeles'))
    notes.append(('CAUTION','Campaign variants','One row may represent one campaign variation, not one distinct campaign; check variant double-counting'))
else: notes.append(('MISSING','Klaviyo_Campaigns_Annual.csv','Campaign CSV could not be parsed'))

if not tables:raise SystemExit('No valid inputs found. Check CSV names and column headers.')
if 'Flow_By_Month' in tables and 'Campaign_By_Month' in tables:
    fm=tables['Flow_By_Month'][['month','revenue','delivered','orders']].rename(columns={'revenue':'flow_revenue','delivered':'flow_delivered','orders':'flow_orders'})
    cm=tables['Campaign_By_Month'][['month','revenue','delivered','orders']].rename(columns={'revenue':'campaign_revenue','delivered':'campaign_delivered','orders':'campaign_orders'})
    comparison=fm.merge(cm,on='month',how='outer').fillna(0).sort_values('month')
    comparison['total_platform_attribution']=comparison.flow_revenue+comparison.campaign_revenue
    tables['Email_Monthly_Comparison']=comparison
    notes.append(('CAUTION','Monthly comparison','Platform attributed flow + campaign revenue is not necessarily unique Shopify revenue; deduplicate using order-level data'))
notes.insert(0,('AUDIT','Coverage',''+str(START.date())+' through '+str(END.date())+'; preliminary attribution-based report'))
notes.insert(1,('LIMITATION','Profit','True email gross/contribution profit requires order-level matching and historical COGS; Shopify storewide profit cannot be assigned to Klaviyo flows'))
notes.insert(2,('LIMITATION','Send-time causality','Send-hour results are descriptive; use holdout/randomized scheduling tests before decisions'))
tables={'Read_Me_Quality':pd.DataFrame(notes,columns=['type','subject','detail']),**tables}
with pd.ExcelWriter(out,engine='openpyxl') as writer:
    for sheet,df in tables.items():
        df.to_excel(writer,sheet_name=sheet,index=False)
        ws=writer.sheets[sheet]
        ws.freeze_panes='A2'
        ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=__import__('openpyxl').styles.Font(bold=True,color='FFFFFF')
            cell.fill=__import__('openpyxl').styles.PatternFill('solid',fgColor='183153')
        for col in ws.columns:
            letter=col[0].column_letter
            maxlen=max((len(str(x.value)) for x in list(col)[:150] if x.value is not None),default=10)
            ws.column_dimensions[letter].width=min(45,max(12,maxlen+2))
print('Created:',out)
print('Worksheets:',', '.join(tables))
for x in notes:
    if x[0] in ('WARNING','READ ERROR'):print(*x,sep=' | ')
