"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { authPost, errorMessage } from "../lib/auth-client";

export function AuthForm({mode}:{mode:"login"|"register"}) {
  const router = useRouter();
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [complete,setComplete] = useState(false);
  const registering = mode === "register";
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const form = new FormData(event.currentTarget);
    const data:Record<string,string> = {email:String(form.get("email")), password:String(form.get("password"))};
    if (registering) data.display_name = String(form.get("display_name"));
    try {
      const response = await authPost(mode,data);
      if (!response.ok) {setError(await errorMessage(response)); return;}
      if (registering) setComplete(true); else router.replace("/account");
    } catch {setError("Không kết nối được dịch vụ. Vui lòng thử lại.");}
    finally {setBusy(false);}
  }
  return <main className="auth-shell"><Link className="brand" href="/">suni<span>AI CINEMA</span></Link>
    <section className="auth-card"><p className="eyebrow">KHÔNG GIAN CỦA BẠN</p>
      <h1>{registering ? "Tạo tài khoản" : "Chào mừng trở lại"}</h1>
      <p className="auth-intro">{registering ? "Bắt đầu cùng Suni với tài khoản Free." : "Đăng nhập để tiếp tục hành trình của bạn."}</p>
      {complete ? <div role="status"><p>Yêu cầu đã được xử lý. Bạn có thể đăng nhập bằng thông tin của mình.</p><Link className="button" href="/login">Đến đăng nhập</Link></div> :
        <form onSubmit={submit}>
          {registering && <label>Tên hiển thị<input name="display_name" autoComplete="nickname" required maxLength={120}/></label>}
          <label>Email<input type="email" name="email" autoComplete="email" required maxLength={254}/></label>
          <label>Mật khẩu<input type="password" name="password" autoComplete={registering ? "new-password":"current-password"} required minLength={12} maxLength={128}/></label>
          <p className="auth-hint">Mật khẩu từ 12 đến 128 ký tự.</p>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="button" disabled={busy}>{busy ? "Đang xử lý…" : registering ? "Đăng ký" : "Đăng nhập"}</button>
        </form>}
      <p className="auth-switch">{registering ? "Đã có tài khoản?" : "Chưa có tài khoản?"} <Link href={registering ? "/login":"/register"}>{registering ? "Đăng nhập":"Đăng ký"}</Link></p>
    </section><Link className="auth-back" href="/">← Về trang chủ</Link>
  </main>;
}
