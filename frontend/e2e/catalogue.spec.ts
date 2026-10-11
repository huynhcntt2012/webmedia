import {expect,test} from '@playwright/test';
test('real catalogue search, pagination, detail and hidden content',async({page},testInfo)=>{
 test.skip(process.env.E2E_AUTH!=='1','Requires isolated catalogue fixtures');
 await page.goto('/movies');await expect(page.getByRole('status').filter({hasText:'28 phim'})).toBeVisible();
 await expect(page.locator('.movie-card')).toHaveCount(24);
 await page.getByRole('link',{name:'Trang sau'}).click();await expect(page.locator('.movie-card')).toHaveCount(4);
 await page.getByLabel('Tìm tên phim').fill('đường về');await page.getByRole('button',{name:'Tìm kiếm'}).click();
 await expect(page.locator('.movie-card')).toHaveCount(1);await expect(page.getByLabel('Tìm tên phim')).toHaveValue('đường về');
 await page.locator('.movie-card').click();await expect(page.getByRole('heading',{name:'Đường Về Mùa Hè'})).toBeVisible();
 await expect(page.getByText('Chưa có bản phát',{exact:true})).toBeVisible();
 await expect(page.locator('.synopsis')).toContainText('<script>');
 expect(await page.evaluate(()=>Object.hasOwn(window,'catalogueXss'))).toBe(false);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:testInfo.outputPath('detail.png'),fullPage:true});
 for(const slug of ['test-draft','test-archived','missing']){await page.goto(`/movies/${slug}`);await expect(page.getByRole('heading',{name:'Không tìm thấy trang'})).toBeVisible();}
 await page.goto('/movies?q=khong-co-ket-qua');await expect(page.getByRole('heading',{name:'Chưa tìm thấy phim phù hợp'})).toBeVisible();
 await page.goto('/movies?page=1001');await expect(page.getByRole('heading',{name:'Tham số tìm kiếm không hợp lệ'})).toBeVisible();
 await page.goto('/movies?sort=title');await page.screenshot({path:testInfo.outputPath('library.png'),fullPage:true});
});
