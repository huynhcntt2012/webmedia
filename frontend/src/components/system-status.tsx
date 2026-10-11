import type { ApiHealth } from "../lib/health";

export function SystemStatus({ state }: { state: ApiHealth }) {
  return <div className={`system-status ${state}`} role="status">
    <span className="status-dot" aria-hidden="true" />
    <div><strong>{state === "ready" ? "API và dữ liệu đã kết nối" : "Đang chờ kết nối dịch vụ"}</strong>
      <p>{state === "ready" ? "FastAPI · PostgreSQL · Redis" : "Khởi động Docker để kiểm tra PostgreSQL và Redis."}</p>
    </div>
  </div>;
}
