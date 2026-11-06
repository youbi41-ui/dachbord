const BACKEND='https://clinic52-youbi.mohamedyoubi.chatgpt.site';
export default { async fetch(request) {
 const incoming=new URL(request.url),security={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','X-Robots-Tag':'noindex, nofollow'};
 if(!['GET','HEAD','POST'].includes(request.method))return new Response('Method not allowed',{status:405,headers:{...security,Allow:'GET, HEAD, POST'}});
 const origin=request.headers.get('Origin');
 if((origin&&origin!==incoming.origin)||(request.method==='POST'&&!origin))return new Response('مصدر الطلب غير مسموح',{status:403,headers:security});
 const target=new URL(BACKEND);target.pathname=incoming.pathname;target.search=incoming.search;
 const headers=new Headers();for(const key of ['accept','accept-language','content-type','cookie','x-csrf-token']){const value=request.headers.get(key);if(value)headers.set(key,value);}
 if(origin)headers.set('Origin',new URL(BACKEND).origin);headers.set('Cache-Control','no-cache');
 try{const response=await fetch(target.toString(),{method:request.method,headers,body:['GET','HEAD'].includes(request.method)?undefined:request.body,redirect:'manual'});
 const output=new Headers(response.headers);for(const [key,value]of Object.entries(security))output.set(key,value);output.delete('Access-Control-Allow-Origin');output.delete('Access-Control-Allow-Credentials');
 const location=output.get('Location');if(location){const next=new URL(location,target);if(next.origin===target.origin){next.protocol=incoming.protocol;next.host=incoming.host;output.set('Location',next.toString());}}
 return new Response(response.body,{status:response.status,statusText:response.statusText,headers:output});
 }catch{return new Response('تعذر الاتصال بخادم العيادة. حاول مرة أخرى بعد قليل.',{status:502,headers:{...security,'Content-Type':'text/plain; charset=utf-8'}});}
}};
