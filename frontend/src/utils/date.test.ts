import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { toIsoDateLocal } from "./date.ts";

describe("toIsoDateLocal", () => {
  test("formats a date as local YYYY-MM-DD", () => {
    assert.equal(toIsoDateLocal(new Date(2026, 0, 5)), "2026-01-05");
  });

  test("pads single-digit month and day", () => {
    assert.equal(toIsoDateLocal(new Date(2026, 8, 3)), "2026-09-03");
  });

  test("uses the local calendar date, not UTC (regression: avoids the\n" +
    "  new Date('YYYY-MM-DD').toISOString() day-shift bug)", () => {
    // Late-evening local time must not roll over to the next UTC day.
    const lateEvening = new Date(2026, 5, 15, 23, 30, 0);
    assert.equal(toIsoDateLocal(lateEvening), "2026-06-15");
  });
});
