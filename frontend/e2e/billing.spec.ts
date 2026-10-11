import {expect,test} from '@playwright/test';
import {createHmac} from 'node:crypto';
test.use({actionTimeout:10000});
test('local billing signed webhook, lost response retry, duplicate and server confirmation',async({page},testInfo)=>{
 test.skip(process.env.E2E_AUTH!=='1','Requires isolated PostgreSQL backend; this is NOT a SePay provider test');test.setTimeout(60000);
 const email=`billing-${testInfo.project.name}-${Date.now()}@example.com`,password='Billing browser test 123!';
 await page.goto('/register');await page.getByLabel('Tên hiển thị').fill('Billing Browser');await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Mật khẩu',{exact:true}).fill(password);await page.getByRole('button',{name:'Đăng ký',exact:true}).click();await expect(page.getByRole('status')).toContainText('Yêu cầu đã được xử lý');
 await page.goto('/login');await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Mật khẩu',{exact:true}).fill(password);await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page).toHaveURL('/account');await page.goto('/plans');
 await expect(page.getByText('Không chuyển tiền thật.',{exact:false})).toBeVisible();
 let lost=false;await page.route('**/api/payments/orders',async route=>{if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort();}else await route.continue();});
 await page.getByRole('button',{name:'Tạo đơn thử VIP',exact:true}).click();await expect(page.locator('.billing [role="alert"]')).toBeVisible();
 const original=(await (await page.request.get('/api/payments/orders')).json()).items[0];expect(original.amount_vnd).toBe(50000);
 await page.getByRole('button',{name:'Tạo đơn thử VIP',exact:true}).click();await expect(page.getByText(`Đã tạo đơn thử nghiệm ${original.payment_code}.`,{exact:true})).toBeVisible();expect((await (await page.request.get('/api/payments/orders')).json()).total).toBe(1);
 await page.goto(`/plans?status=paid&order=${original.id}`);await expect(page.getByText('Chờ xác nhận',{exact:true})).toBeVisible();
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value]));
 const payload={id:Date.now(),gateway:'TestBank',accountNumber:'TEST123456',subAccount:'',code:original.payment_code,content:original.payment_code,transferType:'in',transferAmount:50000,transactionDate:`${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`,referenceCode:'local-browser-fixture'};
 async function deliver(body:object){const raw=JSON.stringify(body),ts=String(Math.floor(Date.now()/1000));return page.request.post('/api/payments/sepay/webhook',{data:raw,headers:{'Content-Type':'application/json','X-SePay-Timestamp':ts,'X-SePay-Signature':'sha256='+createHmac('sha256','e2e-only-webhook-0123456789abcdef0123456789abcdef').update(`${ts}.${raw}`).digest('hex')}});}
 expect((await deliver({...payload,id:payload.id-1,transferAmount:1})).status()).toBe(200);expect((await (await page.request.get(`/api/payments/orders/${original.id}`)).json()).status).toBe('pending');
 expect((await deliver(payload)).status()).toBe(200);expect((await deliver(payload)).status()).toBe(200);expect((await deliver({...payload,transferAmount:1})).status()).toBe(409);
 await page.getByRole('button',{name:'Cập nhật trạng thái',exact:true}).click();await expect(page.getByText('Đã xác nhận',{exact:true})).toBeVisible();await expect(page.getByText(/VIP · Đang hiệu lực/)).toBeVisible();expect((await (await page.request.get('/api/payments/subscriptions')).json()).items).toHaveLength(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:testInfo.outputPath('billing-local.png'),fullPage:true});
});
