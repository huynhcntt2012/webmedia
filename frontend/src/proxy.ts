import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const imageHosts=(process.env.POSTER_ALLOWED_HOSTS??"").split(",").map(h=>h.trim().toLowerCase()).filter(h=>/^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/.test(h)).map(h=>`https://${h}`).join(" ");
  const csp = `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${process.env.NODE_ENV === "development" ? "'unsafe-eval'" : ""}; style-src 'self' 'unsafe-inline'; img-src 'self' data: ${imageHosts}; font-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`;
  const headers = new Headers(request.headers);
  headers.set("Content-Security-Policy",csp);
  headers.set("x-nonce",nonce);
  const response = NextResponse.next({request:{headers}});
  response.headers.set("Content-Security-Policy",csp);
  response.headers.set("Cache-Control","no-store");
  return response;
}

export const config = {matcher:["/((?!api/|_next/static|_next/image|health/|favicon.ico).*)"]};
