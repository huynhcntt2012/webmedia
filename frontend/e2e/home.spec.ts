import {expect,test} from '@playwright/test';
test('catalogue home, keyboard navigation and responsive layout',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await page.goto('/');expect(response?.headers()['x-content-type-options']).toBe('nosniff');
 await expect(page.getByRole('heading',{name:'Mới trong thư viện'})).toBeVisible();
 if(process.env.E2E_AUTH!=='1')await expect(page.getByRole('alert').filter({hasText:'Thư viện đang gián đoạn'})).toBeVisible();
 await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'Đến nội dung chính'})).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 expect(errors).toEqual([]);await page.screenshot({path:testInfo.outputPath('home.png'),fullPage:true});
 await page.getByRole('link',{name:'Tất cả phim'}).click();await expect(page.getByRole('heading',{name:'Thư viện phim',exact:true})).toBeVisible();
});
test('web liveness endpoint',async({request})=>{const response=await request.get('/health/live');expect(response.ok()).toBe(true);expect(await response.json()).toEqual({status:'ok',service:'suni-web'});});
