"""
MediaPipe-basierte Bildnormalisierung für den Overlay-Vergleich.

Ablauf: Landmark-Erkennung (33 Body-Landmarks) -> reine Skalierung +
Verschiebung (KEINE Rotation, KEINE Verzerrung) -> Warp auf feste
Canvas-Größe, damit zwei Fotos möglichst deckungsgleich übereinandergelegt
werden können.

Skalierungs-Referenz ist die tatsächliche Körperhöhe (Kopf bis Fuß), nicht
nur die Rumpflänge - das gleicht unterschiedliche Kameraabstände deutlich
zuverlässiger aus.

Rotation wurde bewusst entfernt: eine automatische "Roll"-Korrektur über
die Schulter-Hüft-Achse hat bei manchen Fotos (z.B. leicht schräg gehaltene
Arme) den Winkel überschätzt und das Bild sichtbar zu stark gedreht -
schlimmer als der ursprüngliche Kamera-Tilt selbst. Da die meisten Handy-
fotos ohnehin fast senkrecht aufgenommen werden, überwiegt der Nutzen
einer Rotationskorrektur den gelegentlichen Fehlerfall nicht. Skalierung
ist zudem so gewählt, dass das Bild garantiert die gesamte Canvas
ausfüllt (kein Letterboxing/schwarze Balken) - dafür wird ggf. etwas mehr
vom Körper angeschnitten als beim reinen Höhen-Ziel.

Bewusst NICHT ausgeglichen: Standbreite, Armhaltung, Kamera-Nickwinkel
("Pitch", z.B. von oben/unten fotografiert). Das sind echte Unterschiede
in Pose/Perspektive, keine reinen Kameraartefakte - sie mit einer
Transform "wegzurechnen" würde den Körper verzerren und die
Vergleichbarkeit der Fortschrittsfotos gerade zerstören. Eine perspektivisch
korrekte Angleichung bräuchte eine echte 3D-Rekonstruktion (MediaPipe liefert
dafür `pose_world_landmarks`) - das ist als spätere Ausbaustufe denkbar,
für den POC aber bewusst außen vor gelassen.

Läuft synchron im Request (POC-Entscheidung: MediaPipe braucht i.d.R.
<1s/Bild, unkritisch beim aktuellen Volumen). Für spätere Skalierung
(viele gleichzeitige Uploads / Cloud) kann dieselbe Funktion problemlos
in einen Background-Task/Queue-Worker verschoben werden, da sie keine
FastAPI-/DB-Abhängigkeiten hat (reine Pfad-zu-Pfad-Funktion).

Hinweis: mediapipe >=1.0 hat die alte `mp.solutions.pose`-API entfernt
zugunsten der neuen Tasks-API (`mediapipe.tasks.python.vision`). Diese
braucht ein separat heruntergeladenes Modell-Bundle (.task-Datei), siehe
MODEL_PATH unten.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).parent / "models" / "pose_landmarker_lite.task"

# Modul-level Singleton: Initialisierung des Landmarkers lädt das Modell
# von Disk, daher nicht pro Request neu instanziieren.
_landmarker = vision.PoseLandmarker.create_from_options(
    vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
    )
)

# Ziel-Canvas für alle normalisierten Bilder (Hochformat, typische
# Ganzkörper-Posefotos).
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1440

# Körper soll diesen Anteil der Canvas-Höhe einnehmen (Kopf bis Fuß);
# der Rest ist Rand oben/unten - sofern die Cover-Regel unten nicht ohnehin
# stärker skaliert (siehe Kommentar bei final_scale).
TARGET_BODY_HEIGHT_RATIO = 0.82
TARGET_TOP_MARGIN_RATIO = 0.09  # nur noch zur Herleitung von height_scale
TARGET_CENTER_X_RATIO = 0.5
TARGET_CENTER_Y_RATIO = 0.5  # Körpermitte (Kopf-Fuß) -> Canvas-Mitte

VISIBILITY_THRESHOLD = 0.5  # für Schultern/Hüften
EXTREMITY_VISIBILITY_THRESHOLD = 0.3  # für Kopf/Fuß-Landmarks (weicher, oft teilverdeckt)

# Grobe anthropometrische Fallback-Verhältnisse (relativ zur Rumpflänge
# Schulter-Mitte -> Hüft-Mitte), falls Kopf- oder Fuß-Landmarks nicht
# sicher erkannt wurden (z.B. Kopf/Füße am Bildrand abgeschnitten).
HEAD_TOP_FALLBACK_RATIO = 0.55  # Kopf-Oberkante ~0.55x Rumpflänge über Schulter-Mitte
FEET_BOTTOM_FALLBACK_RATIO = 2.2  # Fußsohle ~2.2x Rumpflänge unter Hüft-Mitte

_PL = vision.PoseLandmark

# Gelenkpunkte, die für die optionale "Normalisiert+"-Stufe (Comparison-
# spezifischer Pose-Warp, siehe pose_pair_warp.py) im Canvas-Koordinaten-
# system mitgespeichert werden. Bewusst nur die großen, gut erkennbaren
# Gelenke - Hände/Füße-Detailpunkte sind zu instabil für ein robustes Warp.
KEY_JOINTS: list[tuple[str, int]] = [
    ("nose", _PL.NOSE),
    ("left_shoulder", _PL.LEFT_SHOULDER),
    ("right_shoulder", _PL.RIGHT_SHOULDER),
    ("left_elbow", _PL.LEFT_ELBOW),
    ("right_elbow", _PL.RIGHT_ELBOW),
    ("left_wrist", _PL.LEFT_WRIST),
    ("right_wrist", _PL.RIGHT_WRIST),
    ("left_hip", _PL.LEFT_HIP),
    ("right_hip", _PL.RIGHT_HIP),
    ("left_knee", _PL.LEFT_KNEE),
    ("right_knee", _PL.RIGHT_KNEE),
    ("left_ankle", _PL.LEFT_ANKLE),
    ("right_ankle", _PL.RIGHT_ANKLE),
]
KEY_JOINT_VISIBILITY_THRESHOLD = 0.3


@dataclass
class NormalizationResult:
    success: bool
    normalized_path: Path | None
    landmarks_json: str | None
    error: str | None = None


def _landmark_point(landmarks, idx: int, width: int, height: int) -> tuple[float, float, float]:
    lm = landmarks[idx]
    # Tasks-API liefert visibility/presence als eigene Felder je Landmark.
    visibility = getattr(lm, "visibility", 1.0) or 0.0
    return lm.x * width, lm.y * height, visibility


def _apply_affine(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Wendet eine 2x3 cv2-Affinmatrix auf Nx2-Punkte an."""
    homo = np.hstack([points, np.ones((points.shape[0], 1))])
    return (matrix @ homo.T).T


def normalize_photo(source_path: Path, dest_path: Path) -> NormalizationResult:
    """Liest source_path, normalisiert anhand der Ganzkörper-Landmarks und
    schreibt das Ergebnis nach dest_path (Elternordner wird angelegt)."""
    image = cv2.imread(str(source_path))
    if image is None:
        return NormalizationResult(False, None, None, error=f"Bild konnte nicht gelesen werden: {source_path}")

    height, width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = _landmarker.detect(mp_image)

    if not result.pose_landmarks:
        return NormalizationResult(False, None, None, error="Keine Landmarks erkannt")

    lms = result.pose_landmarks[0]  # num_poses=1 -> erste (einzige) erkannte Person
    l_sh = _landmark_point(lms, _PL.LEFT_SHOULDER, width, height)
    r_sh = _landmark_point(lms, _PL.RIGHT_SHOULDER, width, height)
    l_hip = _landmark_point(lms, _PL.LEFT_HIP, width, height)
    r_hip = _landmark_point(lms, _PL.RIGHT_HIP, width, height)

    min_visibility = min(l_sh[2], r_sh[2], l_hip[2], r_hip[2])
    if min_visibility < VISIBILITY_THRESHOLD:
        return NormalizationResult(
            False, None, None,
            error=f"Schulter/Hüfte nicht zuverlässig erkannt (min. Sichtbarkeit {min_visibility:.2f})",
        )

    shoulder_mid = np.array([(l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2])
    hip_mid = np.array([(l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2])
    torso_center = (shoulder_mid + hip_mid) / 2
    torso_vec = hip_mid - shoulder_mid
    torso_length = float(np.linalg.norm(torso_vec))

    if torso_length < 1e-3:
        return NormalizationResult(False, None, None, error="Rumpflänge zu klein (fehlerhafte Landmarks)")

    # --- Kopf-Oberkante bestimmen (für Ganzkörper-Höhenreferenz) ---
    head_candidates = []
    for idx in (_PL.NOSE, _PL.LEFT_EAR, _PL.RIGHT_EAR):
        x, y, vis = _landmark_point(lms, idx, width, height)
        if vis >= EXTREMITY_VISIBILITY_THRESHOLD:
            head_candidates.append(y)
    if head_candidates:
        # Nase/Ohren markieren Augenhöhe, nicht den Scheitel - kleiner
        # Aufschlag nach oben (~12% der Rumpflänge) als Kopf-Anteil.
        head_top_y = min(head_candidates) - 0.12 * torso_length
    else:
        head_top_y = shoulder_mid[1] - HEAD_TOP_FALLBACK_RATIO * torso_length

    # --- Fuß-Unterkante bestimmen ---
    foot_candidates = []
    for idx in (_PL.LEFT_ANKLE, _PL.RIGHT_ANKLE, _PL.LEFT_HEEL, _PL.RIGHT_HEEL,
                _PL.LEFT_FOOT_INDEX, _PL.RIGHT_FOOT_INDEX):
        x, y, vis = _landmark_point(lms, idx, width, height)
        if vis >= EXTREMITY_VISIBILITY_THRESHOLD:
            foot_candidates.append(y)
    if foot_candidates:
        feet_bottom_y = max(foot_candidates)
    else:
        feet_bottom_y = hip_mid[1] + FEET_BOTTOM_FALLBACK_RATIO * torso_length

    body_height = feet_bottom_y - head_top_y
    if body_height < 1e-3:
        return NormalizationResult(False, None, None, error="Körperhöhe konnte nicht bestimmt werden")

    # Skalierung anhand der Körperhöhe (keine Rotation mehr - siehe
    # Moduldoku oben).
    target_body_height_px = TARGET_BODY_HEIGHT_RATIO * CANVAS_HEIGHT
    height_scale = target_body_height_px / body_height

    target_center_x = TARGET_CENTER_X_RATIO * CANVAS_WIDTH
    target_center_y = TARGET_CENTER_Y_RATIO * CANVAS_HEIGHT
    # Vertikaler Anker ist die Körper-MITTE (Kopf-Oberkante bis Fuß-
    # Unterkante gemittelt), NICHT die Kopf-Oberkante. Grund: bei
    # height_scale allein landen Kopf-Oberkante und Fuß-Unterkante dank
    # TARGET_TOP_MARGIN_RATIO=0.09 + TARGET_BODY_HEIGHT_RATIO=0.82 = 0.91
    # symmetrisch bei je 9% Rand oben/unten - Körpermitte trifft also exakt
    # die Canvas-Mitte. Würde man stattdessen (wie früher) IMMER die
    # Kopf-Oberkante starr auf 9% pinnen, würde jede zusätzliche Skalierung
    # durch die Cover-Regel unten (z.B. weil das Bild schmaler ist als
    # gebraucht) komplett auf Kosten des UNTEREN Rands gehen - zwei sonst
    # identisch gerahmte Fotos hätten dann plötzlich unterschiedlich viel
    # Boden/Freiraum unter den Füßen, je nachdem wie stark die Cover-Regel
    # bei genau diesem Foto zuschlägt. Mit der Körpermitte als Anker wird
    # jede zusätzliche Skalierung stattdessen symmetrisch oben UND unten
    # abgeschnitten, was zwischen verschiedenen Fotos konsistent bleibt.
    body_center_y = (head_top_y + feet_bottom_y) / 2

    # Cover-Regel: die Canvas muss immer vollständig mit Bildinhalt gefüllt
    # sein, sonst entstehen schwarze Balken. Anker ist Körpermitte-Y (oben/
    # unten) + Rumpfmitte-X (horizontal) - die Mindest-Skalierung pro Rand
    # daher anhand des tatsächlichen Abstands vom jeweiligen Bildrand zum
    # Anker berechnen (nicht anhand der vollen Bildbreite/-höhe, sonst
    # reicht die Skalierung an einem Rand nicht aus, wenn der Anker nicht
    # exakt in der Bildmitte sitzt).
    def _min_scale_for_edge(anchor: float, edge_to_anchor_target: float, span_to_edge: float) -> float:
        if span_to_edge <= 1e-6:
            return 0.0
        return edge_to_anchor_target / span_to_edge

    cover_scale = max(
        _min_scale_for_edge(body_center_y, target_center_y, body_center_y),  # oberer Rand
        _min_scale_for_edge(body_center_y, CANVAS_HEIGHT - target_center_y, height - body_center_y),  # unterer Rand
        _min_scale_for_edge(torso_center[0], target_center_x, torso_center[0]),  # linker Rand
        _min_scale_for_edge(torso_center[0], CANVAS_WIDTH - target_center_x, width - torso_center[0]),  # rechter Rand
    )
    # Notfalls wird stärker skaliert (= mehr Rand abgeschnitten) als für die
    # reine Körperhöhen-Ratio nötig - das ist der vom Nutzer gewünschte
    # Trade-off ("auf Crop beschränken", keine schwarzen Balken).
    final_scale = max(height_scale, cover_scale)

    # Reine Skalierung + Verschiebung (keine Rotation): torso_center_x auf
    # die Canvas-Mitte, Körpermitte-Y auf die Canvas-Mitte.
    final_matrix = np.array(
        [
            [final_scale, 0.0, target_center_x - final_scale * torso_center[0]],
            [0.0, final_scale, target_center_y - final_scale * body_center_y],
        ],
        dtype=np.float64,
    )

    warped = cv2.warpAffine(
        image, final_matrix, (CANVAS_WIDTH, CANVAS_HEIGHT),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest_path), warped)

    # Die großen Gelenke ins finale Canvas-Koordinatensystem übertragen
    # (dieselbe Matrix wie fürs Bild) und cachen - Grundlage für die
    # "Normalisiert+"-Stufe (siehe pose_pair_warp.py), die zwei bereits
    # normalisierte Bilder zusätzlich aneinander angleicht.
    canvas_landmarks: dict[str, list[float]] = {}
    for name, idx in KEY_JOINTS:
        x, y, vis = _landmark_point(lms, idx, width, height)
        if vis < KEY_JOINT_VISIBILITY_THRESHOLD:
            continue
        cx, cy = _apply_affine(final_matrix, np.array([[x, y]]))[0]
        canvas_landmarks[name] = [float(cx), float(cy), float(vis)]

    landmarks_payload = {
        "shoulder_mid": shoulder_mid.tolist(),
        "hip_mid": hip_mid.tolist(),
        "torso_length_px": torso_length,
        "head_top_y": float(head_top_y),
        "feet_bottom_y": float(feet_bottom_y),
        "body_height_px": body_height,
        "rotation_deg": 0.0,
        "scale": final_scale,
        "source_width": width,
        "source_height": height,
        "canvas_width": CANVAS_WIDTH,
        "canvas_height": CANVAS_HEIGHT,
        "canvas_landmarks": canvas_landmarks,
    }

    return NormalizationResult(
        success=True,
        normalized_path=dest_path,
        landmarks_json=json.dumps(landmarks_payload),
    )
