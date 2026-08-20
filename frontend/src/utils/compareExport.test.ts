// frontend/src/utils/compareExport.test.ts
//
// Ausführen: node --test frontend/src/utils/compareExport.test.ts
// (Node >= 22 führt TypeScript per Type-Stripping direkt aus - kein
// Test-Framework als Dependency nötig.)
//
// Warum es diesen Test gibt
// -------------------------
// Der Compare-Export hat den Bildausschnitt DREIMAL falsch berechnet
// (Commits bbaef73, d731c3e und der zugehörige Fix). Jedes Mal wurde die
// Korrektur nur per Augenmaß an einem Screenshot geprüft - es gab nichts,
// was die Export-Mathematik an die tatsächliche CSS-Semantik der
// Live-Vorschau gebunden hätte.
//
// Dieser Test schließt genau diese Lücke: Er leitet UNABHÄNGIG von der
// Implementierung her, wo ein Punkt des Originalfotos in der Live-Vorschau
// landet - über eine explizite Komposition der CSS-Transformationsmatrizen
// aus Compare.tsx - und prüft, dass der Export exakt dieselbe Abbildung
// liefert, nur um den Faktor k vergrößert.

import assert from "node:assert/strict";
import { test } from "node:test";
import { liveImagePlacement, mapContainerToRegion } from "./compareExport.ts";
import type { LivePaneTransform } from "./compareExport.ts";

// --- Referenz: CSS-Transform-Semantik, unabhängig nachgebaut -------------

/** 2D-Affinmatrix wie CSS sie verwendet: [a, b, c, d, e, f]
 *  x' = a*x + c*y + e ; y' = b*x + d*y + f */
type Mat = [number, number, number, number, number, number];

const IDENTITY: Mat = [1, 0, 0, 1, 0, 0];

/** m1 ∘ m2 - erst m2, dann m1 anwenden (CSS-Reihenfolge: die zuerst
 *  notierte Funktion wirkt zuletzt auf den Punkt). */
function mul(m1: Mat, m2: Mat): Mat {
  return [
    m1[0] * m2[0] + m1[2] * m2[1],
    m1[1] * m2[0] + m1[3] * m2[1],
    m1[0] * m2[2] + m1[2] * m2[3],
    m1[1] * m2[2] + m1[3] * m2[3],
    m1[0] * m2[4] + m1[2] * m2[5] + m1[4],
    m1[1] * m2[4] + m1[3] * m2[5] + m1[5],
  ];
}

const mTranslate = (tx: number, ty: number): Mat => [1, 0, 0, 1, tx, ty];
const mScale = (s: number): Mat => [s, 0, 0, s, 0, 0];
function mRotate(deg: number): Mat {
  const r = (deg * Math.PI) / 180;
  return [Math.cos(r), Math.sin(r), -Math.sin(r), Math.cos(r), 0, 0];
}

/** CSS wendet `transform` um `transform-origin` O an:
 *  effektiv = T(O) ∘ M ∘ T(-O) */
function aroundOrigin(m: Mat, ox: number, oy: number): Mat {
  return mul(mul(mTranslate(ox, oy), m), mTranslate(-ox, -oy));
}

function apply(m: Mat, x: number, y: number): { x: number; y: number } {
  return { x: m[0] * x + m[2] * y + m[4], y: m[1] * x + m[3] * y + m[5] };
}

/**
 * Wo landet ein Punkt des Originalfotos in der Live-Vorschau?
 *
 * Bildet exakt das DOM aus Compare.tsx nach:
 *
 *   <div ref=containerRef class="aspect-[3/4] overflow-hidden">   // W × H
 *     <div style={transformStyle(translate, scale)}>              // origin "0 0"
 *       <img class="h-full w-full object-cover"
 *            style="transform: translate(ox,oy) scale(fz) rotate(r)" />
 *
 * Rückgabe in CSS-Pixeln relativ zur linken oberen Container-Ecke.
 */
function liveScreenPointReference(
  naturalWidth: number,
  naturalHeight: number,
  t: LivePaneTransform,
  naturalX: number,
  naturalY: number
): { x: number; y: number } {
  const W = t.containerWidth;
  const H = t.containerHeight;

  // 1. object-cover: Originalbild wird zentriert in die W×H-Box skaliert.
  const coverScale = Math.max(W / naturalWidth, H / naturalHeight);
  const local = {
    x: W / 2 + coverScale * (naturalX - naturalWidth / 2),
    y: H / 2 + coverScale * (naturalY - naturalHeight / 2),
  };

  // 2. transform des <img> - transform-origin ist per Default die
  //    Elementmitte (50% 50%) = (W/2, H/2).
  const imgTransform = aroundOrigin(
    mul(mul(mTranslate(t.offsetX, t.offsetY), mScale(t.fineZoom)), mRotate(t.rotation)),
    W / 2,
    H / 2
  );

  // 3. transform des äußeren Divs - transform-origin explizit "0 0".
  const outerTransform = aroundOrigin(
    mul(mTranslate(t.translateX, t.translateY), mScale(t.scale)),
    0,
    0
  );

  const afterImg = apply(imgTransform, local.x, local.y);
  return apply(outerTransform, afterImg.x, afterImg.y);
}

// --- Prüfung: Export == Live × k ----------------------------------------

/** Wo platziert die EXPORT-Implementierung denselben Originalbild-Punkt? */
function exportPointFromImplementation(
  region: { x: number; y: number; width: number; height: number },
  naturalWidth: number,
  naturalHeight: number,
  t: LivePaneTransform,
  naturalX: number,
  naturalY: number
): { x: number; y: number } {
  const box = mapContainerToRegion(region, t.containerWidth, t.containerHeight);
  const live = liveImagePlacement(naturalWidth, naturalHeight, t);

  // So zeichnet drawPhotoIntoRegion: Ursprung auf die Bildmitte, drehen,
  // dann das Bild mit live.width/height * k zentriert zeichnen.
  const centerX = box.x + live.centerX * box.k;
  const centerY = box.y + live.centerY * box.k;
  const drawWidth = live.width * box.k;
  const drawHeight = live.height * box.k;

  const relX = (naturalX / naturalWidth - 0.5) * drawWidth;
  const relY = (naturalY / naturalHeight - 0.5) * drawHeight;
  const rot = mRotate(live.rotation);
  const rotated = apply(rot, relX, relY);
  return { x: centerX + rotated.x, y: centerY + rotated.y };
}

function assertExportMatchesLive(
  name: string,
  region: { x: number; y: number; width: number; height: number },
  natural: { width: number; height: number },
  t: LivePaneTransform
) {
  const box = mapContainerToRegion(region, t.containerWidth, t.containerHeight);

  // Mehrere charakteristische Punkte prüfen (Ecken + Mitte), damit auch
  // Skalierungs- und Rotationsfehler auffallen, nicht nur Verschiebungen.
  const probes: Array<[number, number]> = [
    [0, 0],
    [natural.width, 0],
    [0, natural.height],
    [natural.width, natural.height],
    [natural.width / 2, natural.height / 2],
    [natural.width * 0.25, natural.height * 0.75],
  ];

  for (const [nx, ny] of probes) {
    const live = liveScreenPointReference(natural.width, natural.height, t, nx, ny);
    const expected = { x: box.x + live.x * box.k, y: box.y + live.y * box.k };
    const actual = exportPointFromImplementation(region, natural.width, natural.height, t, nx, ny);

    assert.ok(
      Math.abs(actual.x - expected.x) < 0.01 && Math.abs(actual.y - expected.y) < 0.01,
      `${name}: Originalbild-Punkt (${nx}, ${ny}) landet im Export bei ` +
        `(${actual.x.toFixed(2)}, ${actual.y.toFixed(2)}), die Live-Vorschau zeigt ihn aber bei ` +
        `(${expected.x.toFixed(2)}, ${expected.y.toFixed(2)}) - Abweichung ` +
        `(${(actual.x - expected.x).toFixed(2)}, ${(actual.y - expected.y).toFixed(2)}) px`
    );
  }
}

// Reale Werte: 3:4-Container wie in Compare.tsx, echte Fotomaße aus
// Staging (1426x2500), Export-Region = linke Hälfte einer 1080x1080-Canvas.
const CONTAINER = { containerWidth: 650, containerHeight: 866.67 };
const NATURAL = { width: 1426, height: 2500 };
const REGION_SQUARE_HALF = { x: 0, y: 0, width: 540, height: 1080 };
const REGION_43_HALF = { x: 0, y: 0, width: 600, height: 900 };

const base: LivePaneTransform = {
  scale: 1,
  translateX: 0,
  translateY: 0,
  offsetX: 0,
  offsetY: 0,
  fineZoom: 1,
  rotation: 0,
  ...CONTAINER,
};

test("neutraler Zustand (Zoom 1, kein Pan) - war schon vorher korrekt", () => {
  assertExportMatchesLive("neutral", REGION_SQUARE_HALF, NATURAL, base);
});

test("gezoomte Kachel (Zoom 1.40) - der gemeldete Bug", () => {
  // Genau der Zustand aus dem Bug-Report: linke Kachel auf 1.40x gezoomt.
  // transform-origin "0 0" bedeutet, dass scale auch die Bildmitte
  // verschiebt - wurde vom Export ignoriert.
  assertExportMatchesLive("zoom 1.40", REGION_SQUARE_HALF, NATURAL, { ...base, scale: 1.4 });
});

test("gezoomte + geneigte Kachel (Zoom 1.40, -2 Grad)", () => {
  assertExportMatchesLive("zoom + rotation", REGION_SQUARE_HALF, NATURAL, {
    ...base,
    scale: 1.4,
    rotation: -2,
  });
});

test("gezoomt und verschoben (Pan bei Zoom > 1)", () => {
  assertExportMatchesLive("zoom + pan", REGION_SQUARE_HALF, NATURAL, {
    ...base,
    scale: 2.1,
    translateX: -140,
    translateY: -260,
  });
});

test("Slider-Modus: gemeinsamer Zoom plus Feinjustierung pro Bild", () => {
  // Im Slider hat jedes Bild zusätzlich einen eigenen Versatz/Feinzoom auf
  // dem <img> selbst - der liegt INNERHALB des äußeren scale(s) und muss
  // deshalb ebenfalls mit s multipliziert werden.
  assertExportMatchesLive("slider fine-tune", REGION_SQUARE_HALF, NATURAL, {
    ...base,
    scale: 1.35,
    translateX: -60,
    translateY: -95,
    offsetX: 18,
    offsetY: -24,
    fineZoom: 1.12,
    rotation: 3,
  });
});

test("4:3-Export benutzt dieselbe Abbildung", () => {
  assertExportMatchesLive("4:3", REGION_43_HALF, NATURAL, {
    ...base,
    scale: 1.4,
    translateX: -30,
    translateY: -50,
  });
});

test("Querformat-Foto in einem 3:4-Container", () => {
  assertExportMatchesLive("landscape photo", REGION_SQUARE_HALF, { width: 2500, height: 1400 }, {
    ...base,
    scale: 1.25,
  });
});

test("mapContainerToRegion überdeckt die Region vollständig (kein Letterboxing)", () => {
  const box = mapContainerToRegion(REGION_SQUARE_HALF, 650, 866.67);
  assert.ok(box.width >= REGION_SQUARE_HALF.width - 0.01, "Box muss die Region horizontal überdecken");
  assert.ok(box.height >= REGION_SQUARE_HALF.height - 0.01, "Box muss die Region vertikal überdecken");
  // Seitenverhältnis der Box == Seitenverhältnis des Live-Containers.
  assert.ok(Math.abs(box.width / box.height - 650 / 866.67) < 1e-6, "Box muss das Container-Seitenverhältnis behalten");
  // Box ist in der Region zentriert.
  assert.ok(
    Math.abs(
      box.x - (REGION_SQUARE_HALF.x + (REGION_SQUARE_HALF.width - box.width) / 2)
    ) < 1e-6,
    "Box muss horizontal zentriert sein"
  );
});
