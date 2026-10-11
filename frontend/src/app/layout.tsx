import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Suni AI Cinema — Không gian điện ảnh của bạn",
  description: "Khám phá thư viện phim Suni AI Cinema. Tìm câu chuyện tiếp theo dành cho bạn.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi"><body>{children}</body></html>;
}
