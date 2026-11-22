# /// script
# requires-python = ">=3.10"
# dependencies = ["shapely==2.1.2"]
# ///
"""Locate same-net straight-track geometry worth inspecting in EasyEDA Pro. Read only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile


def board_records(path, selector):
    raw = path.read_bytes()
    content = raw
    if path.suffix.lower() == ".epro2":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".epru")]
            if len(names) != 1:
                raise ValueError("Expected one .epru design stream inside the project")
            content = archive.read(names[0])
    elif path.suffix.lower() not in {".epru", ".epcb2"}:
        raise ValueError("Choose a native .epro2, .epru or .epcb2")
    boards = []
    current = None
    for number, line in enumerate(io.StringIO(content.decode("utf-8-sig")), 1):
        if not line.strip():
            continue
        header, sep, payload = line.rstrip("\r\n").removesuffix("|").partition("||")
        if not sep:
            raise ValueError(f"Unrecognized native record at line {number}")
        head = json.loads(header)
        kind = head["type"]
        if kind == "DOCHEAD":
            doc = json.loads(payload)
            current = None
            if doc["docType"] == "PCB":
                current = {"uuid": doc["uuid"], "title": "", "records": []}
                boards.append(current)
        elif current is not None:
            if kind == "META":
                current["title"] = json.loads(payload).get("title", "")
            elif kind in {"LAYER", "LAYER_PHYS", "LINE", "ARC", "POLY", "FILL", "VIA", "POUR"}:
                current["records"].append((kind, head["id"], json.loads(payload)))
    matches = [b for b in boards if selector is None or selector in (b["uuid"], b["title"])]
    if len(matches) != 1:
        raise ValueError("Select one PCB by --pcb UUID or exact title. Available: " +
                         ", ".join(f"{b['title']} ({b['uuid']})" for b in boards))
    return matches[0], hashlib.sha256(raw).hexdigest()


def point_mm(body, end):
    x, y = (float(body[end + axis]) * .0254 for axis in ("X", "Y"))
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("Non-finite native coordinate")
    # 1 nm coordinates stabilize shared endpoints across serialization.
    return round(x, 6), round(y, 6)


def scan(board, short_mm):
    from shapely import STRtree
    from shapely.geometry import LineString
    records = board["records"]
    layers = {}
    for kind, name, values in records:
        if kind == "LAYER_PHYS" and str(values.get("material", "")).lower() == "copper":
            layers[int(json.loads(name)[1])] = True
        elif kind == "LAYER" and values.get("use") and values.get("layerType") in {"TOP", "BOTTOM", "SIGNAL", "PLANE"}:
            layers[int(json.loads(name)[1])] = True
    if not layers:
        raise ValueError("Cannot identify copper layers from this board's layer records")
    grouped = defaultdict(list)
    skipped = Counter()
    findings = []
    def note(kind, net, layer, xy, ids, **extra):
        findings.append(dict(kind=kind, net=net, layer=layer, at_mm=list(xy), objects=sorted(ids), **extra))
    for kind, oid, b in records:
        layer = b.get("layerId")
        if layer not in layers:
            continue
        net = b.get("netName")
        if kind == "LINE" and not net:
            skipped["unassigned_copper_line"] += 1
        elif kind == "LINE":
            a, z = point_mm(b, "start"), point_mm(b, "end")
            if a == z:
                note("zero_length", net, layer, a, [oid])
            else:
                grouped[net, layer].append((oid, a, z))
        elif kind in {"ARC", "POLY", "FILL"} and net:
            skipped[kind] += 1
    if not grouped:
        raise ValueError("No explicitly net-assigned straight copper tracks found")
    junctions = Counter()
    for (net, layer), tracks in grouped.items():
        ends = defaultdict(list)
        shapes = []
        for i, (_, a, b) in enumerate(tracks):
            ends[a].append((i, b))
            ends[b].append((i, a))
            shapes.append(LineString((a, b)))
        tree = STRtree(shapes)
        interior_contacts = set()
        overlaps = set()
        for i, shape in enumerate(shapes):
            for j in tree.query(shape, predicate="intersects"):
                j = int(j)
                if j <= i:
                    continue
                intersection = shape.intersection(shapes[j])
                if intersection.length > 1e-6:
                    pair = sorted((tracks[i][0], tracks[j][0]))
                    note("overlap", net, layer, intersection.interpolate(.5, normalized=True).coords[0],
                         pair, overlap_mm=round(intersection.length, 6))
                    overlaps.add((i, j))
                elif intersection.geom_type == "Point":
                    xy = tuple(round(v, 6) for v in intersection.coords[0])
                    if xy not in tracks[i][1:] or xy not in tracks[j][1:]:
                        interior_contacts.add(xy)
        junctions["mid_track_contacts"] += len(interior_contacts)
        for xy, adjacent in ends.items():
            if xy in interior_contacts:
                continue
            if len(adjacent) > 2:
                junctions["shared_endpoint_branches"] += 1
            if len(adjacent) != 2:
                continue
            (i, a), (j, b) = adjacent
            if (min(i,j), max(i,j)) in overlaps:
                continue
            u = (a[0] - xy[0], a[1] - xy[1])
            v = (b[0] - xy[0], b[1] - xy[1])
            angle = math.degrees(math.atan2(abs(u[0]*v[1] - u[1]*v[0]), u[0]*v[0] + u[1]*v[1]))
            leg = min(math.dist(a, xy), math.dist(b, xy))
            if angle < 88:
                reason = "acute_return"
            elif angle <= 92:
                reason = "right_angle"
            elif short_mm and leg < short_mm and angle < 179:
                reason = "short_leg"
            else:
                continue
            note(reason, net, layer, xy, [tracks[i][0], tracks[j][0]], angle_deg=round(angle, 2), shorter_leg_mm=round(leg, 5))
    return dict(status="inspected", pcb=board["title"], uuid=board["uuid"], copper_layers=sorted(layers),
                assigned_straight_segments=sum(len(t) for t in grouped.values()), named_track_nets=len({k[0] for k in grouped}),
                unanalysed_copper_objects=dict(skipped), junctions=dict(junctions), counts=dict(Counter(f["kind"] for f in findings)),
                candidates=findings, scope="Straight-track centerlines only, including pad and via locations. Confirm pads, branches, arcs, pours and electrical behavior in native CAD and CAM.")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("project", type=Path)
    cli.add_argument("--pcb", help="Exact PCB document UUID or title in a multi-board project")
    cli.add_argument("--short-mm", type=float, help="Additionally list other bends below this shorter-leg length in mm")
    args = cli.parse_args()
    try:
        if args.short_mm is not None and (not math.isfinite(args.short_mm) or args.short_mm <= 0):
            raise ValueError("--short-mm must be a positive finite distance")
        board, digest = board_records(args.project, args.pcb)
        report = scan(board, args.short_mm)
        report["input_sha256"] = digest
    except (ImportError, OSError, ValueError, KeyError, TypeError, IndexError, zipfile.BadZipFile) as exc:
        report = dict(status="review", error=str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "inspected" else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

