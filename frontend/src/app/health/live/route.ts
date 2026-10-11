export async function GET() {
  return Response.json({ status: "ok", service: "suni-web" }, {
    headers: { "Cache-Control": "no-store" },
  });
}
