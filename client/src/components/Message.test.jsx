import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Message from "./Message";

afterEach(cleanup);

it("announces errors at once and offers Try again, with focus on it", () => {
  const retry = vi.fn();
  render(<Message kind="error" text="Can't reach the server." onRetry={retry} />);
  expect(screen.getByRole("alert").textContent).toContain("Can't reach the server.");
  const button = screen.getByRole("button", { name: "Try again" });
  expect(document.activeElement).toBe(button);
  fireEvent.click(button);
  expect(retry).toHaveBeenCalledOnce();
});

it("shows other messages politely, without a button", () => {
  render(<Message kind="warn" text="Waking up the server…" />);
  expect(screen.getByRole("status").textContent).toBe("Waking up the server…");
  expect(screen.queryByRole("button")).toBeNull();
});
