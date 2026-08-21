// frontend/src/utils/compareAspect.test.ts
//
// Ausführen: node --test frontend/src/utils/compareAspect.test.ts

import assert from "node:assert/strict";
import { test } from "node:test";
import { ASPECT_PRESETS, computeAutoAspectRatio, resolveAspectRatio } from "./compareAspect.ts";

test("manuelle Presets werden unverändert zurückgegeben, nicht geklemmt", () => {
  assert.equal(resolveAspectRatio("3:4", undefined, undefined), 3 / 4);
  assert.equal(resolveAspectRatio("4:5", undefined, undefined), 4 / 5);
  assert.equal(resolveAspectRatio("1:1", undefined, undefined), 1);
  assert.equal(resolveAspectRatio("9:16", undefined, undefined), 9 / 16);
});

test("auto: das hochkantigere (kleinere Seitenverhältnis) Foto gewinnt", () => {
  // X: 1000x2000 (0.5, sehr hochkant) - Y: 1000x1250 (0.8, eher quadratisch)
  const photoX = { width: 1000, height: 2000 };
  const photoY = { width: 1000, height: 1250 };
  // 0.5 liegt unter AUTO_MIN_RATIO (9/16 = 0.5625) - wird hochgeklemmt.
  assert.equal(computeAutoAspectRatio(photoX, photoY), ASPECT_PRESETS["9:16"]);
});

test("auto: Ergebnis innerhalb der Preset-Grenzen bleibt unverändert", () => {
  // X: 3:4 (0.75) - Y: 4:5 (0.8) -> min = 0.75, liegt zwischen 9:16 und 4:5.
  const photoX = { width: 900, height: 1200 };
  const photoY = { width: 800, height: 1000 };
  const result = computeAutoAspectRatio(photoX, photoY);
  assert.ok(Math.abs(result - 0.75) < 1e-9, `erwartet 0.75, war ${result}`);
});

test("auto: wird auf die breiteste erlaubte Form (1:1) geklemmt", () => {
  // Beide Fotos landschaft/breiter als hoch (1.2/1.3) - über AUTO_MAX_RATIO
  // (1:1 = 1, jetzt die breiteste Preset-Option) geklemmt.
  const photoX = { width: 1200, height: 1000 };
  const photoY = { width: 1300, height: 1000 };
  assert.equal(computeAutoAspectRatio(photoX, photoY), ASPECT_PRESETS["1:1"]);
});

test("auto: knapp unter der neuen 1:1-Obergrenze bleibt ungeklemmt (vorher wäre das auf 4:5 geklemmt worden)", () => {
  // Beide fast quadratisch (0.95/0.94) - liegt jetzt unterhalb von 1:1,
  // wird also NICHT mehr auf 4:5 heruntergeklemmt.
  const photoX = { width: 950, height: 1000 };
  const photoY = { width: 940, height: 1000 };
  const result = computeAutoAspectRatio(photoX, photoY);
  assert.ok(Math.abs(result - 0.94) < 1e-9, `erwartet 0.94, war ${result}`);
});

test("auto: fehlende Fotomaße fallen auf 3:4 zurück", () => {
  const complete = { width: 900, height: 1200 };
  const missingWidth = { width: null, height: 1200 };
  const missingHeight = { width: 900, height: null };
  assert.equal(computeAutoAspectRatio(complete, missingWidth), 3 / 4);
  assert.equal(computeAutoAspectRatio(missingHeight, complete), 3 / 4);
  assert.equal(computeAutoAspectRatio(undefined, complete), 3 / 4);
});

test('resolveAspectRatio("auto", ...) entspricht computeAutoAspectRatio', () => {
  const photoX = { width: 1000, height: 1500 };
  const photoY = { width: 1000, height: 1400 };
  assert.equal(
    resolveAspectRatio("auto", photoX, photoY),
    computeAutoAspectRatio(photoX, photoY)
  );
});
