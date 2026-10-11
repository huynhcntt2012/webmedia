import { expect, test } from "@playwright/test";

test("auth forms and anonymous account guard", async ({page}) => {
  const response = await page.goto("/login");
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("'nonce-");
  expect(csp.split(";").find(part=>part.includes("script-src"))).not.toContain("'unsafe-inline'");
  await expect(page.getByRole("heading", {name:"Chào mừng trở lại"})).toBeVisible();
  await page.getByRole("link", {name:"Đăng ký", exact:true}).click();
  await expect(page.getByLabel("Tên hiển thị")).toBeVisible();
});

test("real register, login, refresh, user/admin denial and logout", async ({page,context}, testInfo) => {
  test.skip(process.env.E2E_AUTH !== "1", "Requires compose.e2e.yaml");
  const errors:string[]=[];
  page.on("pageerror", error=>errors.push(error.message));
  const email = `browser-${testInfo.project.name}-${Date.now()}@example.com`;
  const password = "Browser test password 123!";
  await page.goto("/register");
  await page.getByLabel("Tên hiển thị").fill("Người xem Suni");
  await page.getByLabel("Email", {exact:true}).fill(email);
  await page.getByLabel("Mật khẩu", {exact:true}).fill(password);
  await page.getByRole("button", {name:"Đăng ký", exact:true}).click();
  await expect(page.getByRole("status")).toContainText("Yêu cầu đã được xử lý");
  await page.getByRole("link", {name:"Đến đăng nhập"}).click();
  await page.getByLabel("Email", {exact:true}).fill(email);
  await page.getByLabel("Mật khẩu", {exact:true}).fill("Incorrect password 123");
  await page.getByRole("button", {name:"Đăng nhập", exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Email hoặc mật khẩu không đúng"})).toBeVisible();
  await page.getByLabel("Mật khẩu", {exact:true}).fill(password);
  await page.getByRole("button", {name:"Đăng nhập", exact:true}).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", {name:"Xin chào, Người xem Suni"})).toBeVisible();
  const cookies = await context.cookies();
  expect(cookies.find(c=>c.name === "suni_refresh")?.httpOnly).toBe(true);
  expect(await page.evaluate(()=>document.cookie)).not.toContain("suni_access");
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  await page.screenshot({path:testInfo.outputPath("account.png"),fullPage:true});
  // Access expiry simulation: keep the refresh cookie and let the real backend rotate it.
  await context.clearCookies({name:"suni_access"});
  await page.reload();
  await expect(page.getByRole("heading", {name:"Xin chào, Người xem Suni"})).toBeVisible();
  expect((await context.cookies()).find(c=>c.name === "suni_refresh")?.value)
    .not.toBe(cookies.find(c=>c.name === "suni_refresh")?.value);
  await page.goto("/admin");
  await expect(page.getByRole("alert").filter({hasText:"không có quyền quản trị"})).toBeVisible();
  await page.goto("/account");
  await page.getByRole("button", {name:"Đăng xuất", exact:true}).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
  expect(errors).toEqual([]);
});
