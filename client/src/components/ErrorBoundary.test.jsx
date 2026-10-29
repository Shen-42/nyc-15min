import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Broken() {
  throw new Error("boom");
}

beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => {}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("shows a message and a Reload button instead of a blank page", () => {
  render(
    <ErrorBoundary name="map">
      <Broken />
    </ErrorBoundary>
  );
  expect(screen.getByRole("alert").textContent).toContain("The map stopped working");
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Reload the page" }));
});

it("keeps the rest of the page working", () => {
  render(
    <>
      <ErrorBoundary name="map">
        <Broken />
      </ErrorBoundary>
      <ErrorBoundary name="panel">
        <p>Score 78</p>
      </ErrorBoundary>
    </>
  );
  expect(screen.getByText("Score 78")).toBeTruthy();
});

it("renders its children when nothing goes wrong", () => {
  render(
    <ErrorBoundary name="panel">
      <p>All good</p>
    </ErrorBoundary>
  );
  expect(screen.queryByRole("alert")).toBeNull();
});
