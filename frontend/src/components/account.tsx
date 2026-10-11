"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authPost, errorMessage, loadUser, type User } from "../lib/auth-client";

export function Account({admin = false}:{admin?:boolean}) {
  const router = useRouter();
  const [user,setUser] = useState<User|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const current = await loadUser();
        if (!active) return;
        if (!current) {router.replace("/login"); return;}
        if (admin) {
          const response = await fetch("/api/admin/check", {cache:"no-store"});
          if (!response.ok) {setError(await errorMessage(response)); return;}
        }
        setUser(current);
      } catch {if (active) setError("Không tải được tài khoản. Vui lòng tải lại trang.");}
    })();
    return () => {active=false;};
  },[router,admin]);
  async function logout(all:boolean) {
    setBusy(true); setError("");
    try {
      const response = await authPost(all ? "logout-all":"logout");
      if (!response.ok) {setError(await errorMessage(response)); return;}
      router.replace("/login"); router.refresh();
    } catch {setError("Không thể đăng xuất. Vui lòng thử lại.");}
    finally {setBusy(false);}
  }
  return <main className="auth-shell"><Link className="brand" href="/">suni<span>AI CINEMA</span></Link>
    <section className="auth-card"><p className="eyebrow">{admin ? "QUẢN TRỊ":"TÀI KHOẢN"}</p>
      <h1>{admin ? "Khu vực quản trị":"Tài khoản của bạn"}</h1>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {!user && !error && <p role="status">Đang kiểm tra phiên đăng nhập…</p>}
      {user && <><h2>Xin chào, {user.display_name}</h2><dl className="account-details">
        <dt>Email</dt><dd>{user.email}</dd><dt>Vai trò</dt><dd>{user.role === "admin" ? "Admin":"User"}</dd>
        <dt>Gói hiện tại</dt><dd>{user.plan_code}</dd><dt>Mã tài khoản</dt><dd>{user.id}</dd></dl>
        {admin ? <p>Quyền quản trị đã được xác minh. Quản lý phim sẽ được mở ở giai đoạn 5.</p> : user.role === "admin" && <Link href="/admin">Vào khu vực quản trị →</Link>}
        <p><Link href="/devices">Quyền nội dung và thiết bị →</Link></p><div className="auth-actions"><button className="button" disabled={busy} onClick={()=>logout(false)}>Đăng xuất</button>
          <button className="text-button" disabled={busy} onClick={()=>logout(true)}>Đăng xuất mọi phiên</button></div></>}
    </section><Link className="auth-back" href="/">← Về trang chủ</Link></main>;
}
