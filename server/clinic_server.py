"""Clinic 52 shared entry server: Python 3.10+, standard library only.
Run setup once, then serve behind the organization's HTTPS reverse proxy.
"""
from __future__ import annotations
import argparse, hashlib, hmac, json, secrets, sqlite3, time, getpass, os, threading, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs
from excel_store import save_snapshot, workbook_bytes

ROOT=Path(__file__).resolve().parents[1]
QATAR=timezone(timedelta(hours=3))
ROLES=('طبيب','تمريض','فني')
def now(): return datetime.now(QATAR).isoformat(timespec='seconds')
def uid(p): return p+'-'+secrets.token_hex(12)
def txt(v,label):
    if not isinstance(v,str) or not v.strip() or len(v.strip())>150 or any(c in v for c in '<>'): raise ValueError('تحقق من '+label)
    return v.strip()
def stamp(v):
    if not isinstance(v,str): raise ValueError('وقت غير صحيح')
    try:
        t=datetime.fromisoformat(v)
        if t.utcoffset()!=timedelta(hours=3): raise ValueError()
        return t
    except (ValueError,TypeError): raise ValueError('التاريخ أو الوقت غير صحيح؛ استخدم توقيت قطر')
def empty():
    d={k:[] for k in ('municipalities','workers','visits','prescriptions','dispensing','services','referrals','stocks','medicalStaff','attendance','shifts','issues','audit')}
    d.update(asOf=now(),synthetic=False,detailSynthetic=False,revision=0,clinics=[{'id':'C52','name':'عيادة سكن 52','camp':'سكن 52'}])
    return d

def optional(v,label):
    if v is None or v=='': return ''
    return txt(v,label)
def demographics(p,at):
    birth=optional(p.get('birthDate'),'تاريخ الميلاد');age=p.get('age')
    if birth:
        try:
            from datetime import date
            parsed=date.fromisoformat(birth)
            if parsed.isoformat()!=birth or birth>at[:10]: raise ValueError()
        except (TypeError,ValueError): raise ValueError('تاريخ الميلاد غير صحيح')
        age=None
    elif age is None or age=='': age=None
    else:
        try:
            f=float(age);age=int(f)
            if f!=age or not 0<=age<=130: raise ValueError()
        except (ValueError,TypeError,OverflowError): raise ValueError('العمر يجب أن يكون عددًا صحيحًا بين 0 و130')
    if birth: age=age_at({'birthDate':birth},at[:10])
    return dict(birthDate=birth,age=age,ageAsOf=at[:10] if age is not None else None,nationality=optional(p.get('nationality'),'الجنسية'),phone=optional(p.get('phone'),'الهاتف'))
def age_at(w,date):
    if w.get('birthDate'):
        b=w['birthDate'];a=int(date[:4])-int(b[:4])-(date[5:10]<b[5:10]);return a if a>=0 else None
    return w.get('age')

def apply(d,op,p,actor):
    at=now(); result=None;before=None;after=None;d.setdefault('prescriptions',[])
    if not isinstance(p,dict): raise ValueError('بيانات غير صحيحة')
    if op=='worker':
        w=dict(id=uid('W'),name=txt(p.get('name'),'اسم العامل'),qid=txt(p.get('qid'),'رقم الهوية'),sap=txt(p.get('sap'),'SAP'),job=txt(p.get('job'),'الوظيفة'),registeredAt=at,**demographics(p,at))
        if any(x['qid']==w['qid'] or x['sap'].lower()==w['sap'].lower() for x in d['workers']): raise ValueError('العامل موجود بالهوية أو SAP؛ ابحث عنه أولًا')
        d['workers'].append(w);result=w['id']
    elif op=='workerUpdate':
        w=next((w for w in d['workers'] if w['id']==p.get('workerId')),None)
        if not w: raise ValueError('ملف العامل غير موجود')
        before=dict(w);fields=dict(name=txt(p.get('name'),'اسم العامل'),qid=txt(p.get('qid'),'رقم الهوية'),sap=txt(p.get('sap'),'SAP'),job=txt(p.get('job'),'الوظيفة'),**demographics(p,at))
        if any(x['id']!=w['id'] and (x['qid']==fields['qid'] or x['sap'].lower()==fields['sap'].lower()) for x in d['workers']): raise ValueError('الهوية أو SAP مستخدمان في ملف عامل آخر')
        if fields['age'] is not None and fields['age']==w.get('age') and not fields['birthDate']: fields['ageAsOf']=w.get('ageAsOf') or at[:10]
        w.update(fields,updatedAt=at);after=dict(w);result=w['id']
    elif op=='visit':
        w=next((w for w in d['workers'] if w['id']==p.get('workerId')),None)
        if not w: raise ValueError('اختر عاملًا مسجلًا')
        if any(v['person']==w['id'] and v.get('status')=='open' for v in d['visits']): raise ValueError('توجد زيارة مفتوحة لهذا العامل؛ استكملها أولًا')
        v=dict(id=uid('V'),clinic='C52',person=w['id'],date=at[:10],arrival=at,hour=int(at[11:13]),municipality='غير محدد',wait=None,emergency=False,response=None,firstEver=not any(v['person']==w['id'] for v in d['visits']),consultationStart=None,status='open',ageAtVisit=age_at(w,at[:10]),ageSource='تاريخ الميلاد' if w.get('birthDate') else 'عمر مسجل' if w.get('age') is not None else 'غير مسجل',workerSnapshot={k:w[k] for k in ('name','qid','sap','job')})
        d['visits'].append(v);result=v['id']
        if 'غير محدد' not in d['municipalities']: d['municipalities'].append('غير محدد')
    elif op=='closeVisit':
        v=next((v for v in d['visits'] if v['id']==p.get('visitId')),None)
        if not v or v.get('status')!='open': raise ValueError('الزيارة غير مفتوحة')
        meds=p.get('meds');no_meds=p.get('noMeds') is True
        if not isinstance(meds,list) or len(meds)>30: raise ValueError('بيانات الأدوية غير صحيحة')
        if not meds and not no_meds: raise ValueError('أضف دواء أو اختر لم يُصرف دواء')
        if meds and no_meds: raise ValueError('أزل خيار لم يُصرف دواء عند إضافة أصناف')
        seen=set(); rows=[];prescriptions=[]
        for m in meds:
            if not isinstance(m,dict): raise ValueError('بيانات الدواء غير صحيحة')
            name=txt(m.get('name'),'اسم الدواء');strength=txt(m.get('strength'),'التركيز');unit=txt(m.get('unit'),'الوحدة')
            try:
                qty=float(m.get('qty') or 0);prescribed=float(m.get('prescribedQty') or 0)
            except (ValueError,TypeError): raise ValueError('كمية غير صحيحة')
            if not 0<=qty<=100000 or not 0<=prescribed<=100000 or not (qty or prescribed): raise ValueError('سجل كمية موصوفة أو مصروفة أكبر من صفر')
            key=(name.lower(),strength.lower(),unit.lower())
            if key in seen: raise ValueError('الصنف مكرر في الزيارة')
            seen.add(key);base=dict(visit=v['id'],drug=uid('DRUG'),name=name+' · '+strength,strength=strength,unit=unit,instructions=optional(m.get('instructions'),'طريقة الاستخدام'),recordedAt=at)
            if qty: rows.append(dict(**base,id=uid('RX'),qty=qty))
            if prescribed: prescriptions.append(dict(**base,id=uid('PR'),qty=prescribed))
        d['dispensing'].extend(rows);d['prescriptions'].extend(prescriptions);v.update(status='closed',closedAt=at,noMeds=no_meds);result=v['id']
    elif op=='staff':
        w=dict(id=uid('MED'),name=txt(p.get('name'),'اسم الكادر'),sap=txt(p.get('sap'),'رقم الموظف'),role=txt(p.get('role'),'المسمى'),clinic='C52')
        if w['role'] not in ROLES: raise ValueError('المسمى غير صحيح')
        if any(x['sap'].lower()==w['sap'].lower() for x in d['medicalStaff']): raise ValueError('رقم الكادر مسجل بالفعل')
        d['medicalStaff'].append(w);result=w['id']
    elif op=='schedule':
        w=next((w for w in d['medicalStaff'] if w['id']==p.get('staffId')),None)
        if not w: raise ValueError('اختر عضو الكادر')
        start=stamp(p.get('start'));end=stamp(p.get('end'));hours=(end-start).total_seconds()/3600
        if not 0<hours<=24: raise ValueError('نهاية الدوام يجب أن تكون بعد البداية وبحد أقصى 24 ساعة')
        if any(a['staffId']==w['id'] and stamp(a['plannedStart'])<end and stamp(a['plannedEnd'])>start for a in d['attendance']): raise ValueError('توجد مناوبة متداخلة لنفس الموظف')
        a=dict(id=uid('ATT'),shiftId='',clinic='C52',staffId=w['id'],role=w['role'],date=start.date().isoformat(),plannedStart=start.isoformat(timespec='seconds'),plannedEnd=end.isoformat(timespec='seconds'),checkIn=None,checkOut=None,requiredHours=hours,actualHours=0,lateMinutes=0,earlyMinutes=0,status='مجدول',scheduled=True)
        d['attendance'].append(a);result=a['id']
    elif op=='attendance':
        a=next((a for a in d['attendance'] if a['id']==p.get('attendanceId')),None);action=p.get('action')
        if not a or action not in ('in','out','absent'): raise ValueError('تحقق من المناوبة والإجراء')
        if action=='absent':
            if a['checkIn'] or a['status']=='غائب' or stamp(a['plannedEnd'])>stamp(at): raise ValueError('يمكن إثبات الغياب بعد انتهاء الدوام دون حضور مسجل')
            a['status']='غائب'
        else:
            t=stamp(p.get('time'))
            if t>stamp(at)+timedelta(minutes=1): raise ValueError('لا يمكن تسجيل وقت فعلي في المستقبل')
            if action=='in':
                if a['checkIn'] or a['status']=='غائب': raise ValueError('سبق تسجيل الحضور أو الغياب')
                if abs((t-stamp(a['plannedStart'])).total_seconds())>86400: raise ValueError('وقت الحضور بعيد عن المناوبة')
                a.update(checkIn=t.isoformat(timespec='seconds'),lateMinutes=max(0,round((t-stamp(a['plannedStart'])).total_seconds()/60)),status='حاضر')
            else:
                if not a['checkIn'] or a['checkOut'] or t<=stamp(a['checkIn']): raise ValueError('سجل الحضور أولًا؛ يجب أن يكون الانصراف بعده')
                hours=(t-stamp(a['checkIn'])).total_seconds()/3600
                if hours>24: raise ValueError('تحقق من تاريخ الانصراف')
                a.update(checkOut=t.isoformat(timespec='seconds'),actualHours=round(hours,2),earlyMinutes=max(0,round((stamp(a['plannedEnd'])-t).total_seconds()/60)),status='مكتمل')
        result=a['id']
    else: raise ValueError('إجراء غير معروف')
    groups={}
    for a in d['attendance']:
        if not a['checkOut'] and a['status']!='غائب': continue
        key=a['date']+'|'+a['role']
        g=groups.setdefault(key,dict(id=key,date=a['date'],clinic='C52',role=a['role'],required=0,actual=0,requiredStaff=0,present=0))
        g['required']+=a['requiredHours'];g['actual']+=min(a['actualHours'],a['requiredHours']);g['requiredStaff']+=1;g['present']+=int(bool(a['checkIn']))
    d['shifts']=list(groups.values());d['revision']+=1;d['asOf']=at;d['audit'].append(dict(id=uid('LOG'),at=at,actor=actor,op=op,recordId=result,**(dict(before=before,after=after) if before else {})))
    return result

def connection(path):
    c=sqlite3.connect(path,timeout=15);c.row_factory=sqlite3.Row;return c

def init_db(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with connection(path) as c:
        c.executescript('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY,role TEXT NOT NULL,salt TEXT NOT NULL,hash TEXT NOT NULL); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,username TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL); CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);')
        c.execute('INSERT OR IGNORE INTO state VALUES(1,?)',(json.dumps(empty(),ensure_ascii=False),))
    try: path.chmod(0o600)
    except OSError: pass

def pw_hash(password,salt): return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
def add_user(path,name,role,password):
    if len(password)<12: raise ValueError('كلمة المرور يجب ألا تقل عن 12 حرفًا')
    salt=secrets.token_hex(16)
    with connection(path) as c: c.execute('INSERT OR REPLACE INTO users VALUES(?,?,?,?)',(name,role,salt,pw_hash(password,salt)));c.execute('DELETE FROM sessions WHERE username=?',(name,))

def save_clinic_user(c,name,password):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,40}',name):
        raise ValueError('اسم المستخدم يجب أن يكون 3 إلى 40 حرفًا إنجليزيًا أو رقمًا أو . _ -')
    if not isinstance(password,str) or len(password)<12:
        raise ValueError('كلمة المرور يجب ألا تقل عن 12 حرفًا')
    salt=secrets.token_hex(16)
    current=c.execute('SELECT role FROM users WHERE name=?',(name,)).fetchone()
    if current and current['role']!='clinic': raise ValueError('اسم المستخدم محجوز لحساب إداري')
    count=c.execute("SELECT COUNT(*) FROM users WHERE role='clinic'").fetchone()[0]
    if not current and count>=5: raise ValueError('تم بلوغ الحد الأقصى: 5 حسابات للعيادة')
    c.execute('INSERT OR REPLACE INTO users VALUES(?,?,?,?)',(name,'clinic',salt,pw_hash(password,salt)))
    c.execute('DELETE FROM sessions WHERE username=?',(name,))
    c.commit()

class Handler(BaseHTTPRequestHandler):
    write_lock=threading.RLock()
    server_version='Clinic52'
    def log_message(self,*args): pass # Never log patient identifiers or payloads.
    def send_json(self,status,body,cookie=None):
        raw=json.dumps(body,ensure_ascii=False,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def session(self,c):
        try: token=SimpleCookie(self.headers.get('Cookie','')).get('clinic52');token=token.value if token else ''
        except Exception: return None
        return c.execute('SELECT s.*,u.role FROM sessions s JOIN users u ON u.name=s.username WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith('/api/'):
            with connection(self.server.db) as c:
                s=self.session(c)
                if path=='/api/session': return self.send_json(200,dict(clinic52=True,user=dict(name=s['username'],role=s['role']) if s else None,csrf=s['csrf'] if s else None))
                if not s: return self.send_json(401,{'error':'انتهت الجلسة؛ سجل الدخول'})
                if path=='/api/data':
                    d=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0]);d.setdefault('prescriptions',[])
                    return self.send_json(200,{'data':d,'excel':getattr(self.server,'excel_status',{'ok':False,'error':'اضغط إعادة حفظ Excel لإنشاء النسخة الحالية'})})
                if path=='/api/excel':
                    d=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0]);worker=parse_qs(urlparse(self.path).query).get('worker',[None])[0]
                    if worker and not any(w['id']==worker for w in d['workers']): return self.send_json(404,{'error':'ملف العامل غير موجود'})
                    raw=workbook_bytes(d,worker);self.send_response(200);self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');self.send_header('Cache-Control','no-store');self.send_header('Content-Disposition','attachment; filename="'+('Worker_File.xlsx' if worker else 'Clinic52_Data.xlsx')+'"');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                if path=='/api/users':
                    if s['role']!='admin': return self.send_json(403,{'error':'إدارة الحسابات لمسؤول النظام فقط'})
                    users=[{'username':u['name']} for u in c.execute("SELECT name FROM users WHERE role='clinic' ORDER BY name")]
                    return self.send_json(200,{'users':users,'limit':5})
                return self.send_json(404,{'error':'مسار غير موجود'})
        if path not in ('/','/dashboard.html','/clinic.html'): return self.send_json(404,{'error':'مسار غير موجود'})
        raw=(ROOT/'dashboard.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        with self.write_lock: self._post()
    def _post(self):
        path=urlparse(self.path).path
        # Same-origin JSON + CSRF token; no CORS is enabled.
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'): return self.send_json(403,{'error':'مصدر الطلب غير مسموح'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send_json(415,{'error':'نوع الطلب غير صحيح'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000: raise ValueError('حجم طلب غير صحيح')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('طلب غير صحيح')
        except Exception: return self.send_json(400,{'error':'طلب غير صحيح'})
        with connection(self.server.db) as c:
            c.execute('BEGIN IMMEDIATE')
            if path=='/api/login':
                ip=self.client_address[0];attempt=c.execute('SELECT * FROM attempts WHERE ip=?',(ip,)).fetchone()
                if attempt and attempt['count']>=8 and attempt['until']>time.time(): return self.send_json(429,{'error':'محاولات كثيرة؛ حاول بعد 15 دقيقة'})
                username=body.get('username');password=body.get('password')
                if not isinstance(username,str) or not isinstance(password,str) or len(password)>500: return self.send_json(400,{'error':'تحقق من بيانات الدخول'})
                u=c.execute('SELECT * FROM users WHERE name=?',(username,)).fetchone();salt=u['salt'] if u else '00'*16;valid=hmac.compare_digest(pw_hash(password,salt),u['hash'] if u else '0'*64)
                if not u or not valid:
                    count=attempt['count']+1 if attempt and attempt['until']>time.time() else 1;c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(ip,count,time.time()+900));c.commit();return self.send_json(401,{'error':'اسم المستخدم أو كلمة المرور غير صحيحة'})
                c.execute('DELETE FROM attempts WHERE ip=?',(ip,));c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,csrf,time.time()+8*3600));c.commit()
                cookie='clinic52='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if self.server.secure_cookie else '')
                return self.send_json(200,dict(user=dict(name=username,role=u['role']),csrf=csrf),cookie)
            s=self.session(c)
            if not s: return self.send_json(401,{'error':'سجل الدخول أولًا'})
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): return self.send_json(403,{'error':'جلسة الطلب غير صحيحة؛ أعد تسجيل الدخول'})
            if path=='/api/logout':
                c.execute('DELETE FROM sessions WHERE token=?',(s['token'],));c.commit();return self.send_json(200,{'ok':True},'clinic52=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path=='/api/users/save':
                if s['role']!='admin': return self.send_json(403,{'error':'إدارة الحسابات لمسؤول النظام فقط'})
                try: save_clinic_user(c,body.get('username'),body.get('password'))
                except ValueError as e: return self.send_json(400,{'error':str(e)})
                return self.send_json(200,{'ok':True,'message':'تم حفظ الحساب وإلغاء جلساته السابقة'})
            if path=='/api/users/disable':
                if s['role']!='admin': return self.send_json(403,{'error':'إدارة الحسابات لمسؤول النظام فقط'})
                username=body.get('username')
                if not isinstance(username,str): return self.send_json(400,{'error':'اسم المستخدم غير صحيح'})
                target=c.execute('SELECT role FROM users WHERE name=?',(username,)).fetchone()
                if not target or target['role']!='clinic': return self.send_json(404,{'error':'حساب العيادة غير موجود'})
                c.execute('DELETE FROM sessions WHERE username=?',(username,));c.execute('DELETE FROM users WHERE name=?',(username,));c.commit()
                return self.send_json(200,{'ok':True,'message':'تم تعطيل الحساب وإنهاء جميع جلساته'})
            if path=='/api/excel/save':
                d=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0]);self.server.excel_status=save_snapshot(self.server.db,d)
                return self.send_json(200,{'excel':self.server.excel_status})
            if path!='/api/command': return self.send_json(404,{'error':'مسار غير موجود'})
            if s['role']!='clinic': return self.send_json(403,{'error':'هذا الحساب للمتابعة فقط'})
            d=json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            if type(body.get('revision')) is not int or body['revision']!=d['revision']: return self.send_json(409,{'error':'تغيرت البيانات بواسطة مستخدم آخر. حدّث السجل ثم أعد الحفظ'})
            try: record=apply(d,body.get('op'),body.get('payload'),s['username'])
            except (ValueError,TypeError,KeyError) as e: return self.send_json(400,{'error':str(e)})
            c.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(d,ensure_ascii=False,allow_nan=False),));c.commit();self.server.excel_status=save_snapshot(self.server.db,d);return self.send_json(200,dict(data=d,id=record,excel=self.server.excel_status))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',type=Path,default=ROOT/'runtime'/'clinic52.sqlite3');parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8080);parser.add_argument('--setup',action='store_true');parser.add_argument('--secure-cookie',action='store_true');args=parser.parse_args();init_db(args.db)
    if args.setup:
        for name,role in (('admin','admin'),('clinic','clinic')):
            print('Set password for '+name+' (minimum 12 characters).')
            password=getpass.getpass('Password: ');confirm=getpass.getpass('Confirm: ')
            if password!=confirm: raise SystemExit('Passwords do not match; run setup again.')
            try: add_user(args.db,name,role,password)
            except ValueError as e: raise SystemExit(str(e))
        print('Accounts saved. Start the server with START_SERVER.bat.')
    else:
        with connection(args.db) as c:
            if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone(): raise SystemExit('Run SETUP_ACCOUNTS.bat first.')
        server=ThreadingHTTPServer((args.host,args.port),Handler);server.db=args.db;server.secure_cookie=args.secure_cookie
        with connection(args.db) as c: server.excel_status=save_snapshot(args.db,json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0]))
        print(f'Clinic 52 server: http://{args.host}:{args.port}/',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
