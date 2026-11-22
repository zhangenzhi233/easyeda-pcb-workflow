"""Compare two independently exported EasyEDA Pro ENET 2.0.0 files by physical pin."""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


class InputError(ValueError):
    """Input does not contain the evidence required for a comparison."""


@dataclass
class Export:
    pins: dict
    footprints: dict
    source_hint: str
    project_id: str
    digest: str
    skipped: list


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def required_str(value, name):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"Missing or invalid {name}")
    return value


def read_enet(path, schematic):
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(data, dict) or data.get("version") != "2.0.0":
        raise InputError("Expected EasyEDA ENET version 2.0.0")
    components = data.get("components")
    if not isinstance(components, dict) or not components:
        raise InputError("Empty or missing component inventory")
    pins, footprints, skipped, hints = {}, {}, [], set()
    for component in components.values():
        if not isinstance(component, dict) or not isinstance(component.get("props"), dict):
            raise InputError("Invalid component or props")
        props = component["props"]
        if schematic and str(props.get("Convert to PCB", "")).strip().lower() == "no":
            skipped.append(str(props.get("Designator") or "(unnamed)"))
            continue
        ref = required_str(props.get("Designator"), "Designator")
        if ref in footprints or "?" in ref:
            raise InputError(f"Duplicate or unannotated reference: {ref}")
        footprints[ref] = props.get("Footprint")
        if "footprintAttrKeys" in component:
            hints.add("pcb")
        elif props.get("Symbol"):
            hints.add("schematic")
        else:
            hints.add("unidentified")
        pin_info = component.get("pinInfoMap")
        if not isinstance(pin_info, dict) or not pin_info:
            raise InputError(f"No physical pin map for {ref}; verify mechanical or logical-only parts separately")
        for entry in pin_info.values():
            if not isinstance(entry, dict):
                raise InputError(f"Invalid pin data for {ref}")
            number = required_str(entry.get("number"), f"{ref} physical pin number")
            key = (ref, number)
            if key in pins:
                raise InputError(f"Multiple entries for {ref}.{number}; inspect shared pad numbers")
            if entry.get("netAmbiguous") or not isinstance(entry.get("net"), str):
                raise InputError(f"Missing or ambiguous network for {ref}.{number}")
            net = entry["net"]
            if net and not net.strip():
                raise InputError(f"Whitespace-only network for {ref}.{number}")
            pins[key] = net
    if not pins:
        raise InputError("No physical pins to compare")
    role = next(iter(hints)) if len(hints) == 1 else "unidentified"
    return Export(pins, footprints, role, data.get("projectId"), hashlib.sha256(raw).hexdigest(), sorted(skipped))


def read_expectations(path):
    if not path:
        return {}
    entries = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        if rows.fieldnames != ["ref", "pin", "net"]:
            raise InputError("Expected CSV header ref,pin,net")
        for row in rows:
            if None in row:
                raise InputError(f"Too many fields on CSV line {rows.line_num}")
            ref, pin, net = (required_str(row.get(k), f"CSV {k} on line {rows.line_num}") for k in rows.fieldnames)
            if (ref, pin) in entries:
                raise InputError(f"Repeated expectation for {ref}.{pin}")
            entries[ref, pin] = "" if net == "@NC" else net
    if not entries:
        raise InputError("Expected-pin CSV is empty")
    return entries


def compare(sch, pcb, expectation_path=None):
    left = read_enet(sch, schematic=True)
    right = read_enet(pcb, schematic=False)
    a, b = left.pins, right.pins
    expected = read_expectations(expectation_path)
    findings = []

    def add(level, kind, **details):
        findings.append(dict(level=level, kind=kind, **details))

    if left.digest == right.digest:
        add("review", "identical_source_bytes", action="Confirm independent schematic and PCB exports")
    for required_side, export in (("schematic", left), ("pcb", right)):
        if export.source_hint not in (required_side, "unidentified"):
            add("review", "unexpected_export_side", expected=required_side, observed_hint=export.source_hint)
    if not left.project_id or not right.project_id:
        add("review", "missing_project_identity")
    elif left.project_id != right.project_id:
        add("review", "different_project_ids", action="Confirm both exports describe the intended revision or variant")
    for ref in sorted(left.footprints.keys() & right.footprints.keys()):
        footprint_a, footprint_b = left.footprints[ref], right.footprints[ref]
        if not footprint_a or not footprint_b or footprint_a != footprint_b:
            add("review", "check_footprint_identity", ref=ref, schematic=footprint_a, pcb=footprint_b,
                action="Compare package, pad dimensions and variant in the native library")
    for ref, pin in sorted(a.keys() | b.keys() | expected.keys()):
        key = (ref, pin)
        details = dict(ref=ref, pin=pin)
        if key not in a or key not in b:
            add("difference", "missing_pin", **details, in_schematic=key in a, in_pcb=key in b)
            continue
        if a[key] != b[key]:
            add("difference", "different_net", **details, schematic=a[key], pcb=b[key])
        if key in expected and (a[key] != expected[key] or b[key] != expected[key]):
            add("difference", "contradicts_pin_table", **details, expected=expected[key], schematic=a[key], pcb=b[key])
        elif key not in expected and (a[key] == "" or b[key] == ""):
            add("review", "unconfirmed_unconnected_pin", **details)
    levels = Counter(item["level"] for item in findings)
    status = "different" if levels["difference"] else "review" if levels["review"] else "match"
    return dict(status=status, schematic_sha256=left.digest, pcb_sha256=right.digest,
                schematic_components_skipped=left.skipped, schematic_pins=len(a), pcb_pins=len(b),
                schematic_nets=len(set(a.values()) - {""}), pcb_nets=len(set(b.values()) - {""}),
                independent_pin_expectations=len(expected), findings=findings)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("schematic", type=Path)
    cli.add_argument("pcb", type=Path)
    cli.add_argument("--expect", type=Path, help="Independent pin table CSV ref,pin,net; @NC confirms an empty pin")
    args = cli.parse_args()
    try:
        report = compare(args.schematic, args.pcb, args.expect)
    except (ValueError, OSError, csv.Error) as error:
        report = dict(status="review", error=str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"match": 0, "different": 1, "review": 2}[report["status"]]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
