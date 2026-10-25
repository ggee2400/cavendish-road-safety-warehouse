#!/usr/bin/env python3
"""MHR/analytics CAT 1: transparent, repeatable cleaning and heatmap generation.
Reads the supplied XLSX with Python's standard zip/XML libraries, retaining reported totals.
No reported count is silently changed and blanks are never treated as zeros.
"""
import argparse
import csv
import math
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

CAUSE_GROUPS = {
    'Population_Behavior': [
        'Careless Driving', 'Reckless Driving', 'Careless Pedestrian',
        'Over Speeding', 'Under Influence of Alcohol',
    ],
    'Road_Environment': ['Dazzled by Lights', 'Obstacle on Carriage Way'],
    'Motor_Vehicle_Condition': ['DMC', 'Over Loading', 'Dangerous Loading'],
}
VARIABLES = [*CAUSE_GROUPS, 'Total_Road_Traffic_Accidents']
OTHER = ['Other Causes', 'Unknown Cause', 'Passenger Falls from Vehicle']
YEAR_LABELS = list(range(2011, 2021))


def read_xlsx_first_sheet(path):
    """Read the original worksheet cells, including sparse/merged headings."""
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared = [''.join(t.text or '' for t in node.iter(ns+'t')) for node in root.findall(ns+'si')]
        sheet_xml = z.read('xl/worksheets/sheet1.xml')
        root = ET.fromstring(sheet_xml)
        rows = {}
        for row in root.iter(ns+'row'):
            r = int(row.get('r', 0)); cells = {}
            for cell in row.findall(ns+'c'):
                ref = cell.get('r', '')
                m = re.match(r'([A-Z]+)', ref)
                if not m: continue
                col = 0
                for char in m.group(1): col = col*26 + ord(char)-64
                typ = cell.get('t')
                val = cell.find(ns+'v')
                if typ == 'inlineStr':
                    node = cell.find(ns+'is')
                    data = ''.join(x.text or '' for x in node.iter(ns+'t')) if node is not None else ''
                elif val is None or val.text is None:
                    data = None
                elif typ == 's': data = shared[int(val.text)]
                elif typ in ('str', 'e'): data = val.text
                else:
                    number = float(val.text)
                    data = int(number) if number.is_integer() else number
                if data not in (None, ''): cells[col] = data
            rows[r] = cells
        return rows


def write_csv(path, names, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        for row in records:
            writer.writerow({k: '' if row.get(k) is None else row[k] for k in names})


def pearson(xs, ys):
    if len(xs)<3: return None
    mx = sum(xs)/len(xs); my=sum(ys)/len(ys)
    denom = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/denom if denom else None


def analyse_source(xlsx, root):
    cells = read_xlsx_first_sheet(xlsx)
    if len(cells)<16: raise ValueError('Expected original 16-row source worksheet')
    if str(cells[2].get(1, '')).strip() != 'Causes of Crashes': raise ValueError('Unexpected workbook header')
    causes = {str(cells[r][1]).strip(): r for r in range(3,16)}
    if len(causes) != 13: raise ValueError(f'Expected 13 cause categories, got {len(causes)}')
    if sorted([name for members in CAUSE_GROUPS.values() for name in members] + OTHER) != sorted(causes):
        raise ValueError('Cause categorisation is incomplete or contains an unknown label')
    yearly=[]; detailed=[]; issues=[]
    for year in YEAR_LABELS:
        start=2+4*(2020-year) if year > 2011 else 38
        if cells[1].get(start) != year: raise ValueError(f'Year header mismatch at {year}: {cells[1].get(start)}')
        totcol = start+3 if year>2011 else start
        reported = cells[16].get(totcol)
        if not isinstance(reported, (int,float)): raise ValueError(f'Missing annual total {year}')
        records={}
        for name,r in causes.items():
            cat={}
            if year>2011:
                for i,key in enumerate(('Fatal','Serious','Minor')):
                    cat[key]=cells[r].get(start+i)
            else:
                for key in ('Fatal','Serious','Minor'): cat[key]=None
            cat['Recorded_Total']=cells[r].get(totcol)
            sev=[cat[k] for k in ('Fatal','Serious','Minor')]
            s=sum(sev) if all(x is not None for x in sev) else None
            delta = cat['Recorded_Total']-s if cat['Recorded_Total'] is not None and s is not None else None
            flag=''
            if cat['Recorded_Total'] is None:
                flag='missing_cause_total'
                issues.append({'Year':year,'Issue':'Missing cause total','Detail':name+' is blank in the supplied spreadsheet','Treatment':'Retained missing; no zero imputation'})
            if delta not in (0,None):
                flag=(';'.join([flag,'severity_sum_mismatch'])).strip(';')
                issues.append({'Year':year,'Issue':'Severity/category total mismatch','Detail':f'{name}: fatal+serious+minor={s}, recorded total={cat["Recorded_Total"]} (difference={delta:+})','Treatment':'Retained recorded category total; flagged row'})
            records[name]=cat['Recorded_Total']
            detailed.append({'Year':year,'Cause':name,**cat,'Severity_Sum':s,'Recorded_minus_Severity':delta,'Quality_Flag':flag,'Source_Row':r})
        yearly_row={'Year':year}
        for col,names in CAUSE_GROUPS.items():
            yearly_row[col] = sum(records[n] for n in names) if all(records[n] is not None for n in names) else None
        yearly_row['Unclassified_or_Ambiguous'] = sum(records[n] for n in OTHER) if all(records[n] is not None for n in OTHER) else None
        yearly_row['Total_Road_Traffic_Accidents'] = reported
        visible=sum(n for n in records.values() if n is not None)
        yearly_row['Sum_of_Listed_Causes'] = visible
        yearly_row['Annual_Total_minus_Listed'] = reported-visible
        yearly_row['Incomplete_Category_Count']=sum(n is None for n in records.values())
        if reported!=visible:
            issues.append({'Year':year,'Issue':'Annual total/category sum discrepancy','Detail':f'Annual total={reported}, visible categories={visible}, difference={reported-visible:+}','Treatment':'Retained published annual total; no invented residual category'})
        if year==2011:
            issues.append({'Year':year,'Issue':'Severity detail not provided','Detail':'2011 only reports category totals; no Fatal/Serious/Minor columns','Treatment':'Left severity columns blank as not provided'})
        yearly.append(yearly_row)
    write_csv(root/'data/cleaned_crash_causes_long.csv', ['Year','Cause','Fatal','Serious','Minor','Recorded_Total','Severity_Sum','Recorded_minus_Severity','Quality_Flag','Source_Row'], detailed)
    write_csv(root/'data/annual_summary.csv', ['Year',*CAUSE_GROUPS,'Unclassified_or_Ambiguous','Total_Road_Traffic_Accidents','Sum_of_Listed_Causes','Annual_Total_minus_Listed','Incomplete_Category_Count'], yearly)
    write_csv(root/'data/data_quality_audit.csv', ['Year','Issue','Detail','Treatment'], sorted(issues,key=lambda x:(x['Year'],x['Issue'])))
    return yearly,issues


def make_heatmap(yearly, root, note='Cleaned data re-imported from GitHub'):
    # Pairwise-complete observations: never turn missing years into zero counts.
    pair_n=[]; correlations=[]
    for a in VARIABLES:
        row=[]; nums=[]
        for b in VARIABLES:
            data=[(float(y[a]),float(y[b])) for y in yearly if y.get(a) is not None and y.get(b) is not None]
            row.append(pearson([z[0] for z in data],[z[1] for z in data]));nums.append(len(data))
        correlations.append(row);pair_n.append(nums)
    write_csv(root/'data/correlation_matrix.csv', ['Variable',*VARIABLES], [dict(Variable=a,**{b:round(c,6) for b,c in zip(VARIABLES,row)}) for a,row in zip(VARIABLES,correlations)])
    write_csv(root/'data/pairwise_observations.csv', ['Variable',*VARIABLES], [dict(Variable=a,**{b:n for b,n in zip(VARIABLES,row)}) for a,row in zip(VARIABLES,pair_n)])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9.4,6.6))
    cmap=plt.get_cmap('RdBu').reversed()
    img=ax.imshow(correlations,vmin=-1,vmax=1,cmap=cmap)
    labels=['Population\nbehaviour','Road\nenvironment','Vehicle\ncondition','Total road\ntraffic accidents']
    ax.set_xticks(range(4),labels,fontsize=10)
    ax.set_yticks(range(4),labels,fontsize=10)
    ax.tick_params(length=0,pad=9)
    for i in range(4):
        for j in range(4):
            r=correlations[i][j]; n=pair_n[i][j]
            ax.text(j,i,f'{r:+.3f}\n(n={n})',ha='center',va='center',fontsize=11,fontweight='bold',color='white' if abs(r)>.65 else '#1c2430')
    ax.set_title('Pearson correlation of annual crash counts (2011–2020)',fontsize=14,fontweight='bold',pad=19)
    fig.colorbar(img,ax=ax,fraction=.044,pad=.04,label='Pearson correlation coefficient (r)')
    fig.text(.5,.015,'Pairwise complete years used. Variable groups are analyst-defined from the source causes.\n'+note,ha='center',fontsize=8.8,color='#475569')
    fig.subplots_adjust(left=.22,right=.93,top=.86,bottom=.18)
    fig.savefig(root/'figures/pearson_correlation_heatmap.png',dpi=220,facecolor='white')
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.0,4.2))
    ax.plot([y['Year'] for y in yearly],[y['Total_Road_Traffic_Accidents'] for y in yearly],marker='o',linewidth=2,color='#234E70')
    ax.set_title('Recorded road traffic accidents by year, 2011–2020',fontsize=13)
    ax.set_xlabel('Year');ax.set_ylabel('Reported crashes')
    ax.set_xticks(YEAR_LABELS);ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(root/'figures/annual_road_accidents.png',dpi=180,facecolor='white');plt.close(fig)
    return correlations,pair_n


def github_download(repo,root):
    import urllib.request
    uri=f'https://raw.githubusercontent.com/{repo}/main/data/annual_summary.csv'
    request=urllib.request.Request(uri,headers={'User-Agent':'CUU-CAT1-Analysis/1.0'})
    with urllib.request.urlopen(request,timeout=25) as response:
        body=response.read().decode('utf-8-sig')
    records=list(csv.DictReader(body.splitlines()))
    for row in records:
        for key in VARIABLES:
            row[key]=float(row[key]) if row[key].strip() else None
        row['Year']=int(row['Year'])
    if len(records)!=10 or [r['Year'] for r in records]!=YEAR_LABELS:
        raise ValueError('GitHub annual summary must contain years 2011..2020')
    return records,uri


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path(__file__).resolve().parent.parent/'data/causes-of-road-traffic-crashes-in-uganda-2011-2020.xlsx')
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent.parent)
    p.add_argument('--github-repo',default='ggee2400/cavendish-road-safety-warehouse')
    p.add_argument('--from-github',action='store_true')
    a=p.parse_args();root=a.output.expanduser().resolve()
    if a.from_github:
        years,url=github_download(a.github_repo,root)
        corr,n=make_heatmap(years,root,'Data fetched from: '+url)
        print('Data imported from GitHub:',url)
    else:
        years,issues=analyse_source(a.input,root)
        corr,n=make_heatmap(years,root,'Source: supplied CUU Excel workbook')
        print('Rows in cleaned long-form table:',len(years)*13)
        print('Data quality issues logged:',len(issues))
        print('Annual totals preserved unchanged: 2011=',years[0]['Total_Road_Traffic_Accidents'],'2020=',years[-1]['Total_Road_Traffic_Accidents'])
    print('Pearson correlation with total accidents:')
    for i in range(3): print(f'  {VARIABLES[i]}: r={corr[i][3]:+.3f}, years={n[i][3]}')
    print('Heatmap:',root/'figures/pearson_correlation_heatmap.png')

if __name__=='__main__': main()
