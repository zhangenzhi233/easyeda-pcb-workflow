# /// script
# requires-python = ">=3.10"
# dependencies = ["gerbonara==1.6.3", "shapely==2.1.2"]
# ///
"""Measure printed ink against mask openings in a standard EasyEDA Gerber ZIP, in mm."""
import argparse
import hashlib
import itertools
import json
import math
import re
import sys
import warnings
import zipfile
from pathlib import Path


def read_layer(archive, ext):
    entries = [entry for entry in archive.infolist()
               if not entry.is_dir() and Path(entry.filename).suffix.upper() == ext]
    if len(entries) != 1:
        raise ValueError(f"Expected one {ext} layer; found {len(entries)}")
    text = archive.read(entries[0]).decode("utf-8-sig")
    if not re.search(r"M0?2\s*\*\s*$", text, re.IGNORECASE):
        raise ValueError(f"Incomplete Gerber end record in {entries[0].filename}")
    if re.search(r"%\s*IPNEG|%\s*SR\s*[XY]|%\s*AB\s*D", text, re.IGNORECASE):
        raise ValueError("Negative image, repeated panel or aperture block needs an independent CAM viewer")
    return entries[0].filename, text


def render_film(text):
    from gerbonara import GerberFile, graphic_primitives
    from gerbonara.utils import MM
    from shapely import make_valid, union_all
    from shapely.geometry import Polygon

    def polygon(primitive):
        arcs = primitive if isinstance(primitive, graphic_primitives.ArcPoly) else primitive.to_arc_poly()
        outline = arcs.approximate_arcs(max_error=0.0001).outline
        return make_valid(Polygon(outline))

    image = Polygon()
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        gerber = GerberFile.from_string(text)
        primitives = (primitive for obj in gerber.objects for primitive in obj.to_primitives(unit=MM))
        for dark, batch in itertools.groupby(primitives, key=lambda item: item.polarity_dark):
            areas = union_all([polygon(item) for item in batch], grid_size=0.00001)
            image = image.union(areas) if dark else image.difference(areas)
    parser_notes = list(dict.fromkeys(str(n.message) for n in notices
                                      if not issubclass(n.category, (DeprecationWarning, PendingDeprecationWarning))))
    return image, parser_notes


def load_labels(path, sides):
    from shapely import from_wkb, from_wkt
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or (data.get("unit"), data.get("view")) != ("mm", "top"):
        raise ValueError("Label references require mm and a single top-view CAM coordinate system")
    records = data.get("labels")
    if not isinstance(records, list) or not records:
        raise ValueError("Expected a non-empty labels list")
    labels, ids = {}, set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Expected an object for each label")
        side, key = row.get("side"), row.get("id")
        if side not in ("top", "bottom") or not isinstance(key, str) or not key.strip() or (side, key) in ids:
            raise ValueError("Each label must specify a board side and have a unique ID per side")
        ids.add((side, key))
        if side not in sides:
            continue
        if ("ink_wkt" in row) == ("ink_wkb" in row):
            raise ValueError(f"Supply one ink_wkt or hex ink_wkb for {key}")
        try:
            ink = from_wkt(row["ink_wkt"]) if "ink_wkt" in row else from_wkb(bytes.fromhex(row["ink_wkb"]))
        except Exception as error:
            raise ValueError(f"Cannot read expected outline for {key}") from error
        if (ink is None or ink.geom_type not in ("Polygon", "MultiPolygon") or
                ink.is_empty or not ink.is_valid or ink.area <= 0 or not all(map(math.isfinite, ink.bounds))):
            raise ValueError(f"Invalid reference geometry for {key}")
        labels.setdefault(side, []).append((key, ink))
    if not labels:
        raise ValueError("No expected labels on the selected side")
    return labels


def verify_labels(actual, labels, tolerance):
    from shapely.geometry import box
    defects = []
    for key, expected in labels:
        # Isolate the glyphs, including their counters. Adjacent artwork needs a separate ROI.
        left, bottom, right, top = expected.bounds
        window = box(left-tolerance, bottom-tolerance, right+tolerance, top+tolerance)
        observed = actual.intersection(window)
        missing = expected.difference(observed.buffer(tolerance)).area
        excess = observed.difference(expected.buffer(tolerance)).area
        if max(missing, excess) > 1e-8:
            defects.append(dict(id=key, box_mm=[round(x, 5) for x in expected.bounds],
                                missing_mm2=round(missing, 8), extra_in_window_mm2=round(excess, 8)))
    return dict(checked=len(labels), matched=len(labels)-len(defects), differences=defects)


def check_side(archive, name, clearance, labels=(), tolerance=.005):
    silk_ext, mask_ext = (".GTO", ".GTS") if name == "top" else (".GBO", ".GBS")
    silk_file, silk = read_layer(archive, silk_ext)
    mask_file, mask = read_layer(archive, mask_ext)
    try:
        ink, warning_a = render_film(silk)
        openings, warning_b = render_film(mask)
    except ImportError:
        raise
    except Exception as error:
        # Third-party parser and topology error classes vary by release.
        raise ValueError(f"Cannot resolve CAM geometry: {type(error).__name__}: {error}") from error
    notes = sorted(set(warning_a + warning_b))
    result = dict(side=name, silk_file=silk_file, mask_file=mask_file,
                  ink_mm2=round(ink.area, 6), openings_mm2=round(openings.area, 6))
    if notes:
        result.update(status="review", parser_warnings=notes)
        return result
    label_error = False
    if labels:
        result["labels"] = verify_labels(ink, labels, tolerance)
        label_error = bool(result["labels"]["differences"])
    if ink.is_empty:
        result.update(status="violation" if label_error else "no_printed_ink")
        return result
    if openings.is_empty:
        result.update(status="violation" if label_error else "review",
                      reason="Mask artwork contains no openings; confirm polarity and board intent")
        return result
    area = ink.intersection(openings)
    gap = ink.distance(openings)
    # Expose unrounded geometry for pass/fail. Rounding is only for presentation.
    violation = area.area > 1e-10 or (clearance > 0 and gap < clearance - 1e-8)
    result.update(status="violation" if violation or label_error else "clear",
                  overlap_mm2=round(area.area, 8), nearest_clearance_mm=round(gap, 6))
    if not area.is_empty and area.area > 1e-10:
        regions = list(getattr(area, "geoms", [area]))
        regions = sorted((r for r in regions if r.area > 1e-10), key=lambda r: -r.area)
        result["overlap_regions"] = len(regions)
        result["largest_overlap_points_mm"] = [
            [round(v, 4) for v in region.representative_point().coords[0]] for region in regions[:8]
        ]
    elif violation:
        from shapely.ops import nearest_points
        p, q = nearest_points(ink, openings)
        result["closest_pair_mm"] = [[round(v, 4) for v in point.coords[0]] for point in (p, q)]
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("zip", type=Path, help="One board, native GTO/GTS and/or GBO/GBS")
    cli.add_argument("--side", choices=["top", "bottom", "both"], default="both")
    cli.add_argument("--clearance-mm", type=float, default=0.0, help="Use the actual board-house clearance")
    cli.add_argument("--labels-json", type=Path, help="Optional independent expected glyphs by side, in top-view board coordinates")
    cli.add_argument("--xy-tolerance-mm", type=float, default=.005, help="Numerical contour tolerance for the optional glyph comparison")
    args = cli.parse_args()
    try:
        if not math.isfinite(args.clearance_mm) or args.clearance_mm < 0:
            raise ValueError("Clearance must be a finite, non-negative mm value")
        if not math.isfinite(args.xy_tolerance_mm) or args.xy_tolerance_mm < 0:
            raise ValueError("Glyph tolerance must be a non-negative finite number")
        selected = ("top", "bottom") if args.side == "both" else (args.side,)
        labels = load_labels(args.labels_json, selected) if args.labels_json else {}
        checked = []
        with zipfile.ZipFile(args.zip) as archive:
            for side in selected:
                try:
                    checked.append(check_side(archive, side, args.clearance_mm, labels.get(side, ()), args.xy_tolerance_mm))
                except (ValueError, KeyError, TypeError, SyntaxError, NotImplementedError, IndexError) as error:
                    checked.append(dict(side=side, status="review", reason=str(error)))
        states = {row["status"] for row in checked}
        if "violation" in states:
            status = "violation"
        elif "review" in states or "clear" not in states:
            status = "review"
        else:
            status = "clear"
        report = dict(status=status, archive_sha256=hashlib.sha256(args.zip.read_bytes()).hexdigest(),
                      required_clearance_mm=args.clearance_mm, sides=checked)
        if args.labels_json:
            report.update(reference_sha256=hashlib.sha256(args.labels_json.read_bytes()).hexdigest(),
                          reference_labels=sum(map(len, labels.values())), xy_tolerance_mm=args.xy_tolerance_mm)
    except (OSError, ImportError, ValueError, zipfile.BadZipFile) as error:
        report = dict(status="review", error=str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"clear": 0, "violation": 1, "review": 2}[report["status"]]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
