export type ApiHealth = "ready" | "unavailable";

export async function getApiHealth(): Promise<ApiHealth> {
  const base = process.env.API_INTERNAL_URL;
  if (!base) return "unavailable";
  try {
    const response = await fetch(`${base}/health/ready`, {
      cache: "no-store", signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return "unavailable";
    const data = await response.json();
    return data.status === "ok" ? "ready" : "unavailable";
  } catch {
    return "unavailable";
  }
}
