/* Clinic 52 entry model. Shared by standalone preview and the test harness. */
const ClinicModel=(()=>{
 const now=()=>new Date(Date.now()+3*3600000).toISOString().slice(0,19)+'+03:00';
 const uid=p=>p+'-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
 const text=(v,label,required=true)=>{v=String(v??'').trim();if((required&&!v)||v.length>150||/[<>]/.test(v))throw Error('تحقق من '+label);return v};
 const stamp=v=>{if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\+03:00$/.test(v)||!Number.isFinite(Date.parse(v)))throw Error('التاريخ أو الوقت غير صحيح');return v};
 const empty=()=>({asOf:now(),synthetic:true,detailSynthetic:true,clinics:[{id:'C52',name:'عيادة سكن 52',camp:'سكن 52'}],municipalities:[],workers:[],visits:[],prescriptions:[],dispensing:[],services:[],referrals:[],stocks:[],medicalStaff:[],attendance:[],shifts:[],issues:[],revision:0,audit:[]});

 function demographics(p,at){
  let birthDate=text(p.birthDate,'تاريخ الميلاد',false),age=p.age===''||p.age===undefined||p.age===null?null:Number(p.age);
  if(birthDate){if(!/^\d{4}-\d{2}-\d{2}$/.test(birthDate)||!Number.isFinite(Date.parse(birthDate+'T12:00:00Z'))||birthDate>at.slice(0,10)||new Date(birthDate+'T12:00:00Z').toISOString().slice(0,10)!==birthDate)throw Error('تاريخ الميلاد غير صحيح');age=null;}
  else if(age!==null&&(!Number.isInteger(age)||age<0||age>130))throw Error('العمر يجب أن يكون عددًا صحيحًا بين 0 و130');
  if(birthDate)age=ageAt({birthDate},at.slice(0,10));
  return {birthDate,age,ageAsOf:age!==null?at.slice(0,10):null,nationality:text(p.nationality,'الجنسية',false),phone:text(p.phone,'الهاتف',false)};
 }
 function ageAt(w,date){if(w.birthDate){let a=Number(date.slice(0,4))-Number(w.birthDate.slice(0,4));if(date.slice(5,10)<w.birthDate.slice(5,10))a--;return a>=0?a:null;}return w.age===undefined||w.age===null||w.age===''?null:Number(w.age);}
 function recompute(d){
  d.shifts=[];const grouped=new Map();
  for(const a of d.attendance){if(!a.checkOut&&a.status!=='غائب')continue;let key=a.date+'|'+a.role;if(!grouped.has(key))grouped.set(key,{id:key,date:a.date,clinic:'C52',role:a.role,required:0,actual:0,requiredStaff:0,present:0});let g=grouped.get(key);g.required+=a.requiredHours;g.actual+=Math.min(a.actualHours,a.requiredHours);g.requiredStaff+=a.scheduled?1:0;g.present+=a.checkIn?1:0;}
  d.shifts=[...grouped.values()];
 }
 function apply(source,op,p,actor='تجربة محلية'){
  const d=structuredClone(source),at=now();d.prescriptions=d.prescriptions||[];let result,before,after;
  if(op==='worker'){
   let w={id:uid('W'),name:text(p.name,'اسم العامل'),qid:text(p.qid,'رقم الهوية'),sap:text(p.sap,'رقم SAP'),job:text(p.job,'الوظيفة'),...demographics(p,at),registeredAt:at};
   if(d.workers.some(x=>x.qid===w.qid||x.sap.toLowerCase()===w.sap.toLowerCase()))throw Error('العامل موجود بالفعل بالهوية أو SAP؛ ابحث عنه أولًا');
   d.workers.push(w);result=w.id;
  }else if(op==='workerUpdate'){
   let w=d.workers.find(x=>x.id===p.workerId);if(!w)throw Error('ملف العامل غير موجود');before=structuredClone(w);
   let fields={name:text(p.name,'اسم العامل'),qid:text(p.qid,'رقم الهوية'),sap:text(p.sap,'SAP'),job:text(p.job,'الوظيفة'),...demographics(p,at)};
   if(d.workers.some(x=>x.id!==w.id&&(x.qid===fields.qid||x.sap.toLowerCase()===fields.sap.toLowerCase())))throw Error('الهوية أو SAP مستخدمان في ملف عامل آخر');
   if(fields.age!==null&&fields.age===w.age&&!fields.birthDate)fields.ageAsOf=w.ageAsOf||at.slice(0,10);
   Object.assign(w,fields,{updatedAt:at});after=structuredClone(w);result=w.id;
  }else if(op==='visit'){
   let w=d.workers.find(x=>x.id===p.workerId);if(!w)throw Error('اختر عاملًا مسجلًا');
   if(d.visits.some(v=>v.person===w.id&&v.status==='open'))throw Error('توجد زيارة مفتوحة لهذا العامل؛ استكملها أولًا');
   let v={id:uid('V'),clinic:'C52',person:w.id,date:at.slice(0,10),arrival:at,hour:Number(at.slice(11,13)),municipality:'غير محدد',wait:null,emergency:false,response:null,firstEver:!d.visits.some(x=>x.person===w.id),consultationStart:null,status:'open',ageAtVisit:ageAt(w,at.slice(0,10)),ageSource:w.birthDate?'تاريخ الميلاد':w.age!==undefined&&w.age!==null?'عمر مسجل':'غير مسجل',workerSnapshot:{name:w.name,qid:w.qid,sap:w.sap,job:w.job}};
   d.visits.push(v);if(!d.municipalities.includes('غير محدد'))d.municipalities.push('غير محدد');result=v.id;
  }else if(op==='closeVisit'){
   let v=d.visits.find(x=>x.id===p.visitId);if(!v||v.status!=='open')throw Error('الزيارة غير مفتوحة');
   if(!Array.isArray(p.meds)||p.meds.length>30)throw Error('بيانات الأدوية غير صحيحة');
   if(!p.meds.length&&!p.noMeds)throw Error('أضف دواء أو اختر لم يُصرف دواء');
   if(p.meds.length&&p.noMeds)throw Error('أزل خيار لم يُصرف دواء عند إضافة أصناف');
   const seen=new Set();
   for(const m of p.meds){let name=text(m.name,'اسم الدواء'),strength=text(m.strength,'تركيز الدواء'),unit=text(m.unit,'وحدة الدواء'),qty=m.qty===''||m.qty===undefined?0:Number(m.qty),prescribedQty=m.prescribedQty===''||m.prescribedQty===undefined?0:Number(m.prescribedQty),instructions=text(m.instructions,'طريقة الاستخدام',false),key=[name,strength,unit].join('|').toLowerCase();
    if(!Number.isFinite(qty)||!Number.isFinite(prescribedQty)||qty<0||prescribedQty<0||qty>100000||prescribedQty>100000||(!qty&&!prescribedQty))throw Error('سجل كمية موصوفة أو مصروفة أكبر من صفر');if(seen.has(key))throw Error('الصنف مكرر في الزيارة');seen.add(key);
    const base={visit:v.id,drug:uid('DRUG'),name:name+' · '+strength,strength,unit,instructions,recordedAt:at};
    if(prescribedQty)d.prescriptions.push({...base,id:uid('PR'),qty:prescribedQty});
    if(qty)d.dispensing.push({...base,id:uid('RX'),qty});
   }v.status='closed';v.closedAt=at;v.noMeds=!!p.noMeds;result=v.id;
  }else if(op==='staff'){
   let w={id:uid('MED'),name:text(p.name,'اسم عضو الكادر'),sap:text(p.sap,'رقم الموظف'),role:text(p.role,'المسمى الطبي'),clinic:'C52'};
   if(!['طبيب','تمريض','فني'].includes(w.role))throw Error('المسمى غير صحيح');if(d.medicalStaff.some(x=>x.sap.toLowerCase()===w.sap.toLowerCase()))throw Error('رقم الكادر مسجل بالفعل');d.medicalStaff.push(w);result=w.id;
  }else if(op==='schedule'){
   let w=d.medicalStaff.find(x=>x.id===p.staffId);if(!w)throw Error('اختر عضو الكادر');let start=stamp(p.start),end=stamp(p.end);let hours=(Date.parse(end)-Date.parse(start))/3600000;
   if(hours<=0||hours>24)throw Error('نهاية الدوام يجب أن تكون بعد البداية وبحد أقصى 24 ساعة');
   if(d.attendance.some(x=>x.staffId===w.id&&x.scheduled&&Date.parse(x.plannedStart)<Date.parse(end)&&Date.parse(x.plannedEnd)>Date.parse(start)))throw Error('توجد مناوبة متداخلة لنفس الموظف');
   let a={id:uid('ATT'),shiftId:'',clinic:'C52',staffId:w.id,role:w.role,date:start.slice(0,10),plannedStart:start,plannedEnd:end,checkIn:null,checkOut:null,requiredHours:hours,actualHours:0,lateMinutes:0,earlyMinutes:0,status:'مجدول',scheduled:true};d.attendance.push(a);result=a.id;
  }else if(op==='attendance'){
   let a=d.attendance.find(x=>x.id===p.attendanceId);if(!a)throw Error('المناوبة غير موجودة');if(!['in','out','absent'].includes(p.action))throw Error('إجراء غير صحيح');
   if(p.action==='absent'){if(a.checkIn||a.status==='غائب'||Date.parse(a.plannedEnd)>Date.parse(at))throw Error('يمكن إثبات الغياب بعد انتهاء الدوام دون حضور مسجل');a.status='غائب';}
   else{let t=stamp(p.time);if(Date.parse(t)>Date.parse(at)+60000)throw Error('لا يمكن تسجيل حضور أو انصراف في المستقبل');
    if(p.action==='in'){if(a.checkIn||a.status==='غائب')throw Error('سبق تسجيل الحضور أو الغياب');if(Math.abs(Date.parse(t)-Date.parse(a.plannedStart))>86400000)throw Error('وقت الحضور بعيد عن المناوبة');a.checkIn=t;a.lateMinutes=Math.max(0,Math.round((Date.parse(t)-Date.parse(a.plannedStart))/60000));a.status='حاضر';}
    else{if(!a.checkIn||a.checkOut||Date.parse(t)<=Date.parse(a.checkIn))throw Error('سجل الحضور أولًا، ويجب أن يكون الانصراف بعده');if(Date.parse(t)-Date.parse(a.checkIn)>86400000)throw Error('تحقق من تاريخ الانصراف');a.checkOut=t;a.actualHours=Math.round((Date.parse(t)-Date.parse(a.checkIn))/36000)/100;a.earlyMinutes=Math.max(0,Math.round((Date.parse(a.plannedEnd)-Date.parse(t))/60000));a.status='مكتمل';}}
   result=a.id;
  }else throw Error('إجراء غير معروف');
  recompute(d);d.revision=(d.revision||0)+1;d.asOf=at;d.audit=d.audit||[];d.audit.push({id:uid('LOG'),at,actor,op,recordId:result,...(before?{before,after}:{})});return {data:d,id:result};
 }
 return {now,empty,apply,ageAt};
})();
if(typeof module!=='undefined')module.exports=ClinicModel;
