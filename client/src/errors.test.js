import { describe, expect, it } from "vitest";
import { errorText, failureText, worthRetrying } from "./errors";

const response = (status, body) => new Response(body === undefined ? "" : JSON.stringify(body), { status });

describe("errorText", () => {
  it("uses the API's message", async () => {
    expect(await errorText(response(422, { detail: "That spot is in Central Park." }))).toBe("That spot is in Central Park.");
  });

  it("reads FastAPI's list-style errors instead of showing [object Object]", async () => {
    const body = { detail: [{ loc: ["query", "lat"], msg: "Input should be a valid number", type: "float_parsing" }] };
    expect(await errorText(response(422, body))).toBe("Input should be a valid number");
  });

  it("falls back to a sentence when there's no readable body", async () => {
    expect(await errorText(response(502))).toMatch(/Something went wrong on our side \(error 502\)/);
    expect(await errorText(response(404), "Not found here.")).toBe("Not found here.");
  });
});

describe("failureText", () => {
  it("tells a timeout from no connection", () => {
    expect(failureText(new DOMException("", "TimeoutError"))).toMatch(/took too long/);
    expect(failureText(new TypeError("Failed to fetch"))).toMatch(/Can't reach the server/);
  });
});

describe("worthRetrying", () => {
  it("retries server errors, not refusals", () => {
    expect(worthRetrying(500)).toBe(true);
    expect(worthRetrying(503)).toBe(true);
    expect(worthRetrying(422)).toBe(false);
    expect(worthRetrying(429)).toBe(false);
  });
});
