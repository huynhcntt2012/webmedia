import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SystemStatus } from "../src/components/system-status";

afterEach(cleanup);
it("shows the actual unavailable status", () => {
  render(<SystemStatus state="unavailable" />);
  expect(screen.getByRole("status")).toHaveTextContent("Đang chờ kết nối dịch vụ");
});
it("shows connected dependencies", () => {
  render(<SystemStatus state="ready" />);
  expect(screen.getByRole("status")).toHaveTextContent("API và dữ liệu đã kết nối");
});
