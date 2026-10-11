import { NextRequest } from "next/server";

const allowed = new Set([
  "GET auth/csrf", "GET auth/me", "GET admin/check", "POST auth/register",
  "POST auth/login", "POST auth/refresh", "POST auth/logout", "POST auth/logout-all",
]);

const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
function allowedAdmin(method:string,path:string) {
  if(['GET','POST'].includes(method)&&path==='admin/comics')return true;
  if(['GET','PUT','DELETE'].includes(method)&&new RegExp(`^admin/comics/${uuid}$`).test(path))return true;
  if(['GET','POST'].includes(method)&&new RegExp(`^admin/comics/${uuid}/chapters$`).test(path))return true;
  if(['PUT','DELETE'].includes(method)&&new RegExp(`^admin/comics/${uuid}/chapters/${uuid}$`).test(path))return true;
  if(['GET','POST'].includes(method)&&new RegExp(`^admin/comics/${uuid}/chapters/${uuid}/pages$`).test(path))return true;
  if(method==='PUT'&&new RegExp(`^admin/comics/${uuid}/chapters/${uuid}/pages/order$`).test(path))return true;
  if(method==='DELETE'&&new RegExp(`^admin/comics/${uuid}/chapters/${uuid}/pages/${uuid}$`).test(path))return true;
  if(method==='GET'&&new RegExp(`^admin/comics/${uuid}/chapters/${uuid}/pages/${uuid}/image$`).test(path))return true;
  if(method === "GET" && new RegExp(`^admin/media-jobs/${uuid}/subtitles$`).test(path))return true;
  if(["PUT","DELETE"].includes(method) && new RegExp(`^admin/media-jobs/${uuid}/subtitles/[a-z]{2,3}(?:-[A-Z]{2})?$`).test(path))return true;
  if(method === "POST" && path === "admin/uploads")return true;
  if(["GET","DELETE"].includes(method) && new RegExp(`^admin/uploads/${uuid}$`).test(path))return true;
  if(method === "PUT" && new RegExp(`^admin/uploads/${uuid}/chunks$`).test(path))return true;
  if(method === "POST" && new RegExp(`^admin/uploads/${uuid}/(complete|retry)$`).test(path))return true;
  if(method === "GET" && new RegExp(`^admin/episodes/${uuid}/uploads$`).test(path))return true;
  if(method === "GET" && new RegExp(`^admin/media-jobs/${uuid}/thumbnail$`).test(path))return true;

  if(method === "GET" && /^admin\/(catalogue-settings|audit-events)$/.test(path))return true;
  if(["GET","POST"].includes(method) && /^admin\/(movies|genres)$/.test(path))return true;
  if(["GET","PUT","DELETE"].includes(method) && new RegExp(`^admin/(movies|genres)/${uuid}$`).test(path))return true;
  if(["GET","POST"].includes(method) && new RegExp(`^admin/movies/${uuid}/episodes$`).test(path))return true;
  return ["PUT","DELETE"].includes(method) && new RegExp(`^admin/movies/${uuid}/episodes/${uuid}$`).test(path);
}

function allowedPlayback(method:string,path:string){
 if(method==='GET' && /^content\/(access|devices)$/.test(path))return true;
 if(method==='DELETE' && new RegExp(`^content/devices/${uuid}$`).test(path))return true;
 if(['GET','POST'].includes(method) && path==='admin/content-grants')return true;
 if(method==='DELETE' && new RegExp(`^admin/content-grants/${uuid}$`).test(path))return true;
 if(method==='GET' && /^(payments\/(plans|orders|subscriptions)|admin\/payment-events)$/.test(path))return true;
 if(method==='GET' && new RegExp(`^payments/orders/${uuid}$`).test(path))return true;
 if(method==='POST' && ['payments/orders','payments/sepay/webhook'].includes(path))return true;
 if(method==='GET' && /^comics(?:\/[a-z0-9]+(?:-[a-z0-9]+)*)?$/.test(path))return true;
 if(method==='GET' && new RegExp(`^reader/chapters/${uuid}(?:/pages/${uuid}/image)?$`).test(path))return true;
 if(method==='PUT' && new RegExp(`^reader/chapters/${uuid}/progress$`).test(path))return true;
 if(method==='GET' && path==='playback/continue')return true;
 if(method==='GET' && new RegExp(`^playback/episodes/${uuid}$`).test(path))return true;
 if(method==='PUT' && new RegExp(`^playback/episodes/${uuid}/progress$`).test(path))return true;
 if(method==='GET' && new RegExp(`^playback/jobs/${uuid}/subtitles/[a-z]{2,3}(?:-[A-Z]{2})?$`).test(path))return true;
 return method==='GET' && new RegExp(`^playback/jobs/${uuid}/media/(master\\.m3u8|[0-9]{2,4}p/(index\\.m3u8|segment_[0-9]{5}\\.ts))$`).test(path);
}

async function forward(request: NextRequest, context: { params: Promise<{path: string[]}> }) {
  const path = (await context.params).path.join("/");
  if (!allowed.has(`${request.method} ${path}`) && !allowedAdmin(request.method,path) && !allowedPlayback(request.method,path)) return Response.json({detail:"Not found"}, {status:404});
  const base = process.env.API_INTERNAL_URL;
  if (!base) return Response.json({detail:"Dịch vụ tài khoản chưa sẵn sàng."}, {status:503});
  const bodyLimit = path==='payments/sepay/webhook' ? 16384 : request.method==='POST' && new RegExp(`^admin/comics/${uuid}/chapters/${uuid}/pages$`).test(path) ? 8*1024*1024 : (request.method === "PUT" && new RegExp(`^admin/uploads/${uuid}/chunks$`).test(path) ? 4*1024*1024 : (new RegExp(`^admin/media-jobs/${uuid}/subtitles/`).test(path) ? 256*1024 : (path.startsWith("admin/") ? 32768 : 8192)));
  let body: Uint8Array | undefined;
  if (["POST","PUT","DELETE"].includes(request.method)) {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      size += value.length;
      if (size > bodyLimit) { await reader.cancel(); return Response.json({detail:"Request too large"}, {status:413}); }
      chunks.push(value);
    }
    body = new Uint8Array(size);
    let offset=0;
    for (const chunk of chunks) {body.set(chunk,offset); offset+=chunk.length;}
  }
  try {
    const headers = new Headers();
    for (const key of ["cookie", "origin", "content-type", "x-csrf-token", "x-chunk-sha256", "range", "x-sepay-signature", "x-sepay-timestamp"]) {
      const value = request.headers.get(key);
      if (value) headers.set(key, value);
    }
    const upstream = await fetch(`${base}/${path}${request.nextUrl.search}`, {
      method:request.method, headers, body:body as BodyInit | undefined,
      cache:"no-store", redirect:"error", signal:AbortSignal.timeout(path.startsWith('admin/comics/')?25000:10000),
    });
    const responseHeaders = new Headers({"Cache-Control":"no-store"});
    for (const key of ["content-type", "retry-after", "content-range", "accept-ranges"]) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key,value);
    }
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("Set-Cookie",cookie);
    return new Response(upstream.body, {status:upstream.status, headers:responseHeaders});
  } catch {
    return Response.json({detail:"Không kết nối được dịch vụ tài khoản. Vui lòng thử lại."}, {status:503});
  }
}

export const GET = forward;
export const POST = forward;

export const PUT = forward;
export const DELETE = forward;
