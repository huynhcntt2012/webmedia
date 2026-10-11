export type User = {id:string; email:string; display_name:string; role:"user"|"admin"; plan_code:string};

async function locked<T>(name:string, action:()=>Promise<T>):Promise<T> {
  return typeof navigator !== "undefined" && navigator.locks
    ? navigator.locks.request(name,action) : action();
}

export async function csrfRequest(path:string, method:string, data?:unknown, chunkHash?:string) {
  return locked("suni-auth-write", async () => {
    const csrf = await fetch("/api/auth/csrf", {cache:"no-store"});
    if (!csrf.ok) return csrf;
    const {csrf_token} = await csrf.json();
    return fetch(`/api/${path}`, {method, headers:{
      "Content-Type":chunkHash?"application/octet-stream":"application/json", "X-CSRF-Token":csrf_token, ...(chunkHash?{"X-Chunk-SHA256":chunkHash}:{}),
    }, body:chunkHash ? data as BodyInit : JSON.stringify(data ?? {})});
  });
}

export function authPost(path:string,data?:unknown){return csrfRequest(`auth/${path}`,"POST",data);}

export async function loadUser():Promise<User|null> {
  const read = () => fetch("/api/auth/me", {cache:"no-store"});
  let response = await read();
  if (response.status === 401) {
    response = await locked("suni-session-refresh", async () => {
      const check = await read(); // Another tab may already have refreshed.
      if (check.status !== 401) return check;
      return authPost("refresh");
    });
  }
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Không tải được tài khoản. Vui lòng thử lại.");
  return (await response.json()).user;
}

export async function errorMessage(response:Response) {
  try { return (await response.json()).detail || "Yêu cầu chưa thành công. Vui lòng thử lại."; }
  catch { return "Yêu cầu chưa thành công. Vui lòng thử lại."; }
}
