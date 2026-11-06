"""Populate the shipped Artifact Tool-authored Excel layout using standard OOXML packaging."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from io import BytesIO
from datetime import datetime
import json,html,re,os,math
ROOT=Path(__file__).resolve().parents[1]
LAYOUT=json.loads((ROOT/'excel_layout.json').read_text())
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
def xml(v):return html.escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v)),quote=True)
def col(i):
    s='';i+=1
    while i:i,r=divmod(i-1,26);s=chr(65+r)+s
    return s
def serial(v,t):
    if t=='n':return float(v)
    if t=='t':
        v=v[11:19] if 'T' in v else v;a=list(map(int,v.split(':')));return (a[0]*3600+a[1]*60+(a[2] if len(a)>2 else 0))/86400
    d=datetime.fromisoformat(v[:19]);return (d-datetime(1899,12,30)).total_seconds()/86400

def data_rows(d,worker_id=None):
    wm={w['id']:w for w in d['workers']};sm={w['id']:w for w in d['medicalStaff']};vs=[v for v in d['visits'] if not worker_id or v['person']==worker_id];vm={v['id']:v for v in vs};workers=[]
    for w in d['workers']:
        if worker_id and w['id']!=worker_id:continue
        vv=sorted((v for v in vs if v['person']==w['id']),key=lambda x:x['arrival'],reverse=True)
        workers.append([w['id'],w['name'],w['qid'],w['sap'],w.get('birthDate'),w.get('age'),w.get('ageAsOf'),w['job'],w.get('nationality'),w.get('phone'),w.get('registeredAt'),len(vv),vv[0]['arrival'] if vv else None])
    visits=[];drugs=[];days=['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد']
    for v in vs:
        w=v.get('workerSnapshot') or wm.get(v['person'],{});visits.append([v['id'],v['person'],w.get('name'),w.get('qid'),w.get('sap'),v['date'],days[datetime.fromisoformat(v['date']).weekday()],v['arrival'],v.get('closedAt'),'مفتوحة' if v.get('status')=='open' else 'مغلقة' if v.get('status')=='closed' else 'سجل سابق',v.get('ageAtVisit'),v.get('ageSource'),v.get('workerSnapshot',{}).get('job')])
    for events,label in ((d.get('prescriptions',[]),'موصوف'),(d['dispensing'],'مصروف')):
        for m in events:
            v=vm.get(m['visit'])
            if not v:continue
            w=v.get('workerSnapshot') or wm.get(v['person'],{});name=m.get('name') or next((x['name'] for x in d['stocks'] if x['drug']==m['drug']),m['drug']);drugs.append([m['id'],v['id'],v['person'],w.get('name'),w.get('sap'),v['date'],v['arrival'],label,name,m['qty'],m['unit'],m.get('instructions'),m.get('recordedAt')])
    out=[workers,visits,drugs]
    if worker_id:return out
    out.append([[w['id'],w['name'],w['sap'],w['role']] for w in d['medicalStaff']]);out.append([[a['id'],sm.get(a['staffId'],{}).get('name'),sm.get(a['staffId'],{}).get('sap'),a['role'],a['date'],a['plannedStart'],a['plannedEnd'],a['checkIn'],a['checkOut'],a['requiredHours'],a['actualHours'],a['lateMinutes'],a['earlyMinutes'],a['status']] for a in d['attendance']]);out.append([[a['id'],a['at'],a['actor'],a['op'],a['recordId'],json.dumps(a['before'],ensure_ascii=False) if a.get('before') else '',json.dumps(a['after'],ensure_ascii=False) if a.get('after') else ''] for a in d.get('audit',[])])
    return out

def worksheet(spec,rows):
    def cell(v,i,r,header=False):
        ref=col(i)+str(r);style=spec['headerStyle'] if header else spec['styles'][i];t='s' if header else spec['columns'][i][1]
        if v is None or v=='':return f'<c r="{ref}" s="{style}"/>'
        if t!='s':return f'<c r="{ref}" s="{style}"><v>{serial(v,t)}</v></c>'
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml(v)}</t></is></c>'
    header='<row r="1" ht="44" customHeight="1">'+''.join(cell(c[0],i,1,True) for i,c in enumerate(spec['columns']))+'</row>';data=''.join(f'<row r="{i+2}" ht="{max(27,min(300,max((math.ceil(len(str(v or ''))/24)*17+10 for v in row),default=27)))}" customHeight="1">'+''.join(cell(v,j,i+2) for j,v in enumerate(row))+'</row>' for i,row in enumerate(rows));end=col(len(spec['columns'])-1)+str(max(1,len(rows)+1));cols=''.join(f'<col min="{i+1}" max="{i+1}" width="{44 if re.match(r"رقم (الملف|السجل|العملية|الزيارة|ملف العامل|الكادر)",c[0]) else 34 if "اسم" in c[0] or "الدواء" in c[0] else 26}" customWidth="1"/>' for i,c in enumerate(spec['columns']))
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}"><dimension ref="A1:{end}"/><sheetViews><sheetView rightToLeft="1" showGridLines="0" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{header+data}</sheetData><autoFilter ref="A1:{end}"/></worksheet>'

def workbook_bytes(d,worker_id=None):
    rows=data_rows(d,worker_id);specs=LAYOUT['schema'][:len(rows)];out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('xl/styles.xml',LAYOUT['styles']);z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(specs)))+'</Types>');z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>');z.writestr('xl/workbook.xml',f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{s["name"]}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i,s in enumerate(specs))+'</sheets></workbook>');z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(specs)))+'<Relationship Id="rStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        for i,(s,r) in enumerate(zip(specs,rows)):z.writestr(f'xl/worksheets/sheet{i+1}.xml',worksheet(s,r))
    return out.getvalue()

def save_snapshot(db_path,d):
    target=Path(db_path).parent/'Clinic52_Data.xlsx';temp=target.with_suffix('.xlsx.tmp')
    try:
        temp.write_bytes(workbook_bytes(d));os.replace(temp,target)
        return {'ok':True,'revision':d['revision'],'file':'Clinic52_Data.xlsx'}
    except OSError:
        try:temp.unlink(missing_ok=True)
        except OSError:pass
        return {'ok':False,'revision':d['revision'],'file':'Clinic52_Data.xlsx','error':'تعذر تحديث Excel. أغلق الملف إذا كان مفتوحًا وتحقق من صلاحية المجلد، ثم اضغط إعادة حفظ Excel.'}
