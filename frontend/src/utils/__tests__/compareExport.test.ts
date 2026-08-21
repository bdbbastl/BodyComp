// frontend/src/utils/__tests__/compareExport.test.ts
// Run with: node --test src/utils/__tests__/compareExport.test.ts
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  shouldShowWatermark,
  renderSideBySideToCanvas,
  renderSliderToCanvas,
} from "../compareExport.ts";

/** Minimalistischer CanvasRenderingContext2D-Mock, der jeden Aufruf
 * protokolliert - genug Oberfläche für compareExport.ts, kein echtes
 * Rendering (kein `canvas`-npm-Paket als Testabhängigkeit nötig). */
function createMockContext() {
  const calls: string[] = [];
  const props: Record<string, unknown> = {};
  const ctx: Record<string, unknown> = {
    save: () => calls.push("save"),
    restore: () => calls.push("restore"),
    beginPath: () => calls.push("beginPath"),
    rect: () => calls.push("rect"),
    clip: () => calls.push("clip"),
    translate: () => calls.push("translate"),
    rotate: () => calls.push("rotate"),
    drawImage: () => calls.push("drawImage"),
    fillRect: () => calls.push("fillRect"),
    fill: () => calls.push("fill"),
    fillText: (text: string) => calls.push(`fillText:${text}`),
    moveTo: () => calls.push("moveTo"),
    lineTo: () => calls.push("lineTo"),
    stroke: () => calls.push("stroke"),
    roundRect: () => calls.push("roundRect"),
    measureText: () => ({ width: 120 }),
  };
  for (const key of ["fillStyle", "strokeStyle", "font", "textAlign", "textBaseline", "lineWidth", "filter"]) {
    Object.defineProperty(ctx, key, {
      get: () => props[key],
      set: (v) => {
        props[key] = v;
      },
    });
  }
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

function createMockCanvas(mockCtx: CanvasRenderingContext2D) {
  return {
    width: 0,
    height: 0,
    getContext: () => mockCtx,
  } as unknown as HTMLCanvasElement;
}

function fakeImage(): HTMLImageElement {
  return { naturalWidth: 400, naturalHeight: 400 } as unknown as HTMLImageElement;
}

const paneState = { scale: 1, translateX: 0, translateY: 0, rotation: 0, brightness: 100 };

describe("shouldShowWatermark", () => {
  test("undefined user (not yet loaded) defaults to showing the watermark", () => {
    assert.equal(shouldShowWatermark(undefined), true);
  });

  test("paying coach (active) is exempt", () => {
    assert.equal(shouldShowWatermark({ account_type: "coach", subscription_status: "active" }), false);
  });

  test("trialing coach is exempt", () => {
    assert.equal(shouldShowWatermark({ account_type: "coach", subscription_status: "trialing" }), false);
  });

  test("non-paying coach requires the watermark", () => {
    assert.equal(shouldShowWatermark({ account_type: "coach", subscription_status: null }), true);
  });

  test("single account with an active plan still requires the watermark", () => {
    assert.equal(shouldShowWatermark({ account_type: "single", subscription_status: "active" }), true);
  });
});

describe("watermark rendering", () => {
  test("renderSideBySideToCanvas draws the watermark text and a legible backdrop behind it when showWatermark=true", () => {
    const withWatermark = createMockContext();
    renderSideBySideToCanvas(
      createMockCanvas(withWatermark.ctx),
      "1:1",
      fakeImage(),
      paneState,
      fakeImage(),
      paneState,
      true
    );
    const withoutWatermark = createMockContext();
    renderSideBySideToCanvas(
      createMockCanvas(withoutWatermark.ctx),
      "1:1",
      fakeImage(),
      paneState,
      fakeImage(),
      paneState,
      false
    );

    const textIndex = withWatermark.calls.findIndex((c) => c === "fillText:BodyComp Tracker");
    assert.notEqual(textIndex, -1, "watermark text should be drawn");

    // A backdrop (fillRect/roundRect) must be drawn behind the text so it stays
    // legible against arbitrary photo backgrounds - compare against the
    // no-watermark run (which still has the base canvas-background fillRect)
    // to isolate a *dedicated* watermark backdrop shape.
    const shapeCount = (calls: string[]) => calls.filter((c) => c === "fillRect" || c === "roundRect").length;
    assert.ok(
      shapeCount(withWatermark.calls) > shapeCount(withoutWatermark.calls),
      "an extra backdrop shape should be drawn behind the watermark text, beyond the base canvas background fill"
    );

    // The backdrop shape must be drawn before (i.e. behind) the text.
    const lastShapeBeforeText = withWatermark.calls
      .slice(0, textIndex)
      .some((c) => c === "fillRect" || c === "roundRect");
    assert.ok(lastShapeBeforeText, "backdrop shape must precede (render behind) the watermark text");
  });

  test("renderSideBySideToCanvas draws nothing watermark-related when showWatermark=false", () => {
    const { ctx, calls } = createMockContext();
    const canvas = createMockCanvas(ctx);
    renderSideBySideToCanvas(canvas, "1:1", fakeImage(), paneState, fakeImage(), paneState, false);

    assert.equal(calls.some((c) => c.startsWith("fillText:BodyComp")), false);
  });

  test("renderSliderToCanvas draws the watermark with a backdrop when showWatermark=true", () => {
    const sliderState = {
      scale: 1,
      translateX: 0,
      translateY: 0,
      dividerPct: 50,
      x: { offsetX: 0, offsetY: 0, fineZoom: 1, rotation: 0, brightness: 100 },
      y: { offsetX: 0, offsetY: 0, fineZoom: 1, rotation: 0, brightness: 100 },
    };

    const withWatermark = createMockContext();
    renderSliderToCanvas(createMockCanvas(withWatermark.ctx), "1:1", fakeImage(), fakeImage(), sliderState, true);
    const withoutWatermark = createMockContext();
    renderSliderToCanvas(createMockCanvas(withoutWatermark.ctx), "1:1", fakeImage(), fakeImage(), sliderState, false);

    const textIndex = withWatermark.calls.findIndex((c) => c === "fillText:BodyComp Tracker");
    assert.notEqual(textIndex, -1, "watermark text should be drawn");

    const shapeCount = (calls: string[]) => calls.filter((c) => c === "fillRect" || c === "roundRect").length;
    assert.ok(
      shapeCount(withWatermark.calls) > shapeCount(withoutWatermark.calls),
      "an extra backdrop shape should be drawn behind the watermark text"
    );
  });
});
