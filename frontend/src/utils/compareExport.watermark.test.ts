// frontend/src/utils/compareExport.watermark.test.ts
//
// Ausführen: node --test frontend/src/utils/compareExport.watermark.test.ts
//
// Deckt die Wasserzeichen-Sichtbarkeit ab: die Konto/Abo-Fallunterscheidung
// in shouldShowWatermark() (Design-Spec "Compare-Export für Social Media",
// Abschnitt "Sichtbarkeit / Wasserzeichen-Logik im Detail") sowie den
// Bugfix, dass der Wasserzeichen-Text auf hellen Foto-Hintergründen ohne
// Hintergrund-Chip praktisch unsichtbar war (Bug-Report vom User).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  shouldShowWatermark,
  renderSideBySideToCanvas,
  renderSliderToCanvas,
} from "./compareExport.ts";

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
    closePath: () => calls.push("closePath"),
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
    arcTo: () => calls.push("arcTo"),
    stroke: () => calls.push("stroke"),
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

const paneState = {
  scale: 1,
  translateX: 0,
  translateY: 0,
  rotation: 0,
  brightness: 100,
  containerWidth: 300,
  containerHeight: 400,
};

const sliderState = {
  scale: 1,
  translateX: 0,
  translateY: 0,
  dividerPct: 50,
  containerWidth: 300,
  containerHeight: 400,
  x: { offsetX: 0, offsetY: 0, fineZoom: 1, rotation: 0, brightness: 100 },
  y: { offsetX: 0, offsetY: 0, fineZoom: 1, rotation: 0, brightness: 100 },
};

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
  test("renderSideBySideToCanvas draws the watermark text with a filled backdrop chip when showWatermark=true", () => {
    const { ctx, calls } = createMockContext();
    const canvas = createMockCanvas(ctx);
    renderSideBySideToCanvas(canvas, "1:1", fakeImage(), paneState, fakeImage(), paneState, true);

    const textIndex = calls.findIndex((c) => c === "fillText:BodyComp Tracker");
    assert.notEqual(textIndex, -1, "watermark text should be drawn");

    // The backdrop chip is a filled path (beginPath/arcTo.../fill), distinct
    // from the plain fillRect used to clear the canvas background - without
    // it, semi-transparent white text alone disappears on light photos.
    const fillIndex = calls.findIndex((c, i) => i < textIndex && c === "fill");
    assert.notEqual(fillIndex, -1, "a filled backdrop shape should be drawn behind the watermark text");
  });

  test("renderSideBySideToCanvas draws nothing watermark-related when showWatermark=false", () => {
    const { ctx, calls } = createMockContext();
    const canvas = createMockCanvas(ctx);
    renderSideBySideToCanvas(canvas, "1:1", fakeImage(), paneState, fakeImage(), paneState, false);

    assert.equal(calls.some((c) => c.startsWith("fillText:BodyComp")), false);
    assert.equal(calls.includes("fill"), false);
  });

  test("renderSliderToCanvas draws the watermark with a backdrop when showWatermark=true", () => {
    const { ctx, calls } = createMockContext();
    const canvas = createMockCanvas(ctx);
    renderSliderToCanvas(canvas, "1:1", fakeImage(), fakeImage(), sliderState, true);

    const textIndex = calls.findIndex((c) => c === "fillText:BodyComp Tracker");
    assert.notEqual(textIndex, -1, "watermark text should be drawn");
    const fillIndex = calls.findIndex((c, i) => i < textIndex && c === "fill");
    assert.notEqual(fillIndex, -1, "a filled backdrop shape should be drawn behind the watermark text");
  });
});
