import {expect,test} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
test.use({actionTimeout:10000});

test('reader vertical scroll, page mode, keyboard, bookmark resume and revoked chapter',async({page},testInfo)=>{
 test.skip(process.env.E2E_AUTH!=='1','Requires real isolated backend');test.setTimeout(90000);
 await page.goto('/login');await page.getByLabel('Email',{exact:true}).fill('admin-browser@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('E2E-only-password-123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page).toHaveURL('/account');
 const csrf=(await (await page.request.get('/api/auth/csrf')).json()).csrf_token;
 const headers={'Origin':'http://localhost:3100','X-CSRF-Token':csrf};
 const slug=`reader-${testInfo.project.name}-${Date.now()}`;
 const comic=await (await page.request.post('/api/admin/comics',{headers,data:{title:`Reader ${slug}`,slug,status:'published'}})).json();
 const chapter=await (await page.request.post(`/api/admin/comics/${comic.id}/chapters`,{headers,data:{title:'Chương đọc thử',chapter_number:1}})).json();
 const bytes=Buffer.from(execFileSync('docker',['compose','-f','../compose.e2e.yaml','exec','-T','worker','python','-c','import io,base64; from PIL import Image; b=io.BytesIO(); Image.new("RGB",(320,640),"#829e56").save(b,format="PNG"); print(base64.b64encode(b.getvalue()).decode())'],{encoding:'utf8'}).trim(),'base64');
 const base=`/api/admin/comics/${comic.id}/chapters/${chapter.id}/pages`;
 try {
  for(let version=1;version<=3;version++){const r=await page.request.post(`${base}?version=${version}&upload_key=${randomUUID()}`,{headers:{...headers,'Content-Type':'application/octet-stream','X-Chunk-SHA256':createHash('sha256').update(bytes).digest('hex')},data:bytes});expect(r.status()).toBe(201);}
  await page.goto('/comics');await page.getByLabel('Tìm tên truyện').fill(slug);await page.getByRole('button',{name:'Tìm truyện',exact:true}).click();await page.getByRole('link',{name:`Reader ${slug}`,exact:true}).click();await page.getByRole('link',{name:'Chương 1: Chương đọc thử',exact:true}).click();
  await expect(page).toHaveURL(`/read/${chapter.id}`);
  const readerURL=page.url(),viewport=page.getByLabel('Nội dung chương');
  await expect(page.getByRole('heading',{name:'Chương đọc thử'})).toBeVisible();await expect(page.getByLabel('Chế độ đọc')).toHaveValue('vertical');
  await expect.poll(()=>page.getByAltText('Trang truyện 1',{exact:true}).evaluate((e:HTMLImageElement)=>e.naturalWidth)).toBe(320);
  await viewport.evaluate(el=>{const first=el.querySelector('figure')!;el.scrollTop=first.getBoundingClientRect().height*1.3;});
  await expect(page.getByLabel('Trang đang đọc')).toHaveValue('1');
  const saved=page.waitForResponse(async r=>r.url().endsWith('/progress')&&r.request().method()==='PUT'&&r.status()===200&&r.request().postDataJSON().offset_milli>200);
  await page.getByRole('button',{name:'Lưu vị trí',exact:true}).click();await saved;await expect(page.getByRole('status')).toHaveText('Đã lưu vị trí đọc.');
  await page.reload();await expect(page.getByLabel('Trang đang đọc')).toHaveValue('1');await expect.poll(()=>viewport.evaluate(el=>{const h=el.querySelector('figure')!.getBoundingClientRect().height;return el.scrollTop/h;})).toBeGreaterThan(1.2);
  await page.getByLabel('Chế độ đọc').selectOption('paged');await expect(viewport.locator('img')).toHaveCount(1);
  await viewport.focus();await page.keyboard.press('ArrowRight');await expect(page.getByLabel('Trang đang đọc')).toHaveValue('2');await expect(page.getByRole('button',{name:'Trang sau',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Lưu vị trí',exact:true}).click();await expect(page.getByRole('status')).toHaveText('Đã lưu vị trí đọc.');
  await page.goto('/comics');await page.goto(readerURL);await expect(page.getByLabel('Chế độ đọc')).toHaveValue('paged');await expect(page.getByLabel('Trang đang đọc')).toHaveValue('2');await expect.poll(()=>page.getByAltText('Trang truyện 3',{exact:true}).evaluate((e:HTMLImageElement)=>e.naturalWidth)).toBe(320);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:testInfo.outputPath('comic-reader.png'),fullPage:true});
  await page.goto('/devices');await expect(page.getByRole('heading',{name:'Thiết bị đang xem và đọc'})).toBeVisible();await expect(page.getByRole('button',{name:'Thu hồi phiên hiện tại',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:testInfo.outputPath('devices.png'),fullPage:true});await page.goto(readerURL);
  const currentCsrf=(await (await page.request.get('/api/auth/csrf')).json()).csrf_token;
  const r=await page.request.put(`/api/admin/comics/${comic.id}`,{headers:{...headers,'X-CSRF-Token':currentCsrf},data:{title:comic.title,slug,status:'draft',version:1}});expect(r.status()).toBe(200);
  await page.reload();await expect(page.locator('.comic-library [role="alert"]')).toContainText('không còn được xuất bản');await expect(page.locator('.reader-viewport img')).toHaveCount(0);
 } finally {
  const fresh=(await (await page.request.get('/api/auth/csrf')).json()).csrf_token;
  const row=await (await page.request.get(`/api/admin/comics/${comic.id}`)).json();
  expect((await page.request.delete(`/api/admin/comics/${comic.id}?version=${row.version}`,{headers:{...headers,'X-CSRF-Token':fresh}})).status()).toBe(204);
 }
});
