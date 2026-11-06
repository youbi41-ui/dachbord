# رابط Cloudflare مجاني للعيادة

هذا المجلد ينشر واجهة مرور على Cloudflare Workers، ويُبقي خادم الحسابات والسجلات وExcel في الاستضافة الحالية. يظهر للمستخدم رابط workers.dev، بينما تُنقل الطلبات إلى الخادم الحالي. لا يتضمن بيانات مرضى أو كلمات مرور. يجب إبقاء الخادم الحالي فعالًا؛ هذه إضافة لرابط الدخول وليست نقلًا لقاعدة البيانات.

في حساب Cloudflare المحدد: Workers & Pages → Create application → GitHub → youbi41-ui/dachbord.

الإعدادات:
- Worker name: clinic52-platform
- Production branch: main
- Root directory: cloudflare-link
- Build command: npm run build
- Deploy command: npx wrangler deploy

اختر الخطة المجانية عند عرض خيارات الخطة. لا يحتاج هذا المجلد إلى D1 أو R2 في حسابك. بعد Save and Deploy يعرض Cloudflare عنوان workers.dev الفعلي؛ لا يمكن تحديد عنوانه النهائي قبل النشر. ادخل بالاسم وكلمة المرور نفسيهما المستخدمين في المنصة الحالية.

اجتاز المصدر 15 فحصًا للتحقق من المصدر والصلاحيات المنقولة وملفات تعريف الارتباط وحماية التخزين المؤقت ومعالجة فشل الخادم. اختبر تسجيل الدخول وحفظ زيارة وتنزيل Excel عبر الرابط الجديد بعد نشره.
