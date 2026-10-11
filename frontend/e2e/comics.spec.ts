import {expect,test} from '@playwright/test';
import {execFileSync} from 'node:child_process';

test('admin comic CRUD, image batch partial failure, retry, reorder and cleanup',async({page},testInfo)=>{
 test.skip(process.env.E2E_AUTH!=='1','Requires isolated real API and decoder');test.setTimeout(90000);
 const suffix=`${testInfo.project.name}-${Date.now()}`,title=`Truyện ${suffix}`;
 page.on('dialog',dialog=>void dialog.accept());
 const images=JSON.parse(execFileSync('docker',['compose','-f','../compose.e2e.yaml','exec','-T','worker','python','-c',
  'import io,json,base64; from PIL import Image; result=[]\nfor color in ["red","blue"]:\n b=io.BytesIO(); Image.new("RGB",(320,480),color).save(b,format="PNG"); result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))'],{encoding:'utf8',timeout:30000}));
 await page.goto('/login');await page.getByLabel('Email',{exact:true}).fill('admin-browser@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('E2E-only-password-123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page).toHaveURL('/account');
 await page.goto('/admin');await page.getByRole('link',{name:'Truyện tranh',exact:true}).click();
 await page.getByRole('button',{name:'Tạo truyện',exact:true}).click();await page.getByLabel('Tên truyện',{exact:true}).fill(title);await page.getByLabel('Slug truyện',{exact:true}).fill(`comic-${suffix}`);await page.getByLabel('Mô tả truyện',{exact:true}).fill('<script>window.comicXss=true</script>');
 await page.getByRole('button',{name:'Lưu truyện',exact:true}).click();await expect(page.getByText('Đã lưu truyện.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Thêm chương',exact:true}).click();await page.getByLabel('Tên chương',{exact:true}).fill('Chương mở đầu');await page.getByRole('button',{name:'Lưu chương',exact:true}).click();await expect(page.getByText('Đã lưu chương.',{exact:true})).toBeVisible();
 await page.getByLabel('Chọn nhiều ảnh',{exact:true}).setInputFiles([
  {name:'01-red.png',mimeType:'image/png',buffer:Buffer.from(images[0],'base64')},
  {name:'02-broken.png',mimeType:'image/png',buffer:Buffer.from('<svg><script>bad</script></svg>')},
  {name:'03-blue.png',mimeType:'image/png',buffer:Buffer.from(images[1],'base64')},
 ]);
 await page.getByRole('button',{name:'Tải ảnh / thử lại ảnh lỗi',exact:true}).click();
 await expect(page.locator('.comic-page-grid > li')).toHaveCount(2,{timeout:30000});
 await expect(page.locator('.upload-results')).toContainText('02-broken.png — Ảnh cần');
 await expect.poll(()=>page.getByAltText('Trang 1',{exact:true}).evaluate((img:HTMLImageElement)=>img.naturalWidth)).toBe(320);
 await page.getByRole('button',{name:'Tải ảnh / thử lại ảnh lỗi',exact:true}).click();await expect(page.getByRole('button',{name:'Tải ảnh / thử lại ảnh lỗi',exact:true})).toBeEnabled();await expect(page.locator('.comic-page-grid > li')).toHaveCount(2);
 const second=await page.locator('.comic-page-grid > li').nth(1).getAttribute('data-page-id');
 await page.getByRole('button',{name:'Đưa trang 2 lên',exact:true}).click();await expect(page.getByText('Đã lưu thứ tự trang.',{exact:true})).toBeVisible();
 await expect(page.locator('.comic-page-grid > li').first()).toHaveAttribute('data-page-id',second!);
 await page.getByRole('button',{name:'Tải lại trang chương',exact:true}).click();await expect(page.locator('.comic-page-grid > li').first()).toHaveAttribute('data-page-id',second!);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>Object.hasOwn(window,'comicXss'))).toBe(false);
 await page.screenshot({path:testInfo.outputPath('comic-pages.png'),fullPage:true});
 await page.getByRole('button',{name:'Xóa trang 1',exact:true}).click();await expect(page.locator('.comic-page-grid > li')).toHaveCount(1);await expect(page.getByAltText('Trang 1',{exact:true})).toBeVisible();
 await page.getByLabel('Tên chương',{exact:true}).fill('Chương đã sửa');await page.getByRole('button',{name:'Lưu chương',exact:true}).click();await expect(page.getByRole('button',{name:'Mở chương Chương đã sửa',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Xóa chương',exact:true}).click();await expect(page.getByText('Đã xóa chương.',{exact:true})).toBeVisible();
 await page.getByLabel('Tên truyện',{exact:true}).fill(`${title} sửa`);await page.getByRole('button',{name:'Lưu truyện',exact:true}).click();await expect(page.getByRole('button',{name:`Sửa truyện ${title} sửa`,exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Xóa truyện',exact:true}).click();await expect(page.getByText('Đã xóa truyện và ảnh liên quan.',{exact:true})).toBeVisible();
});
