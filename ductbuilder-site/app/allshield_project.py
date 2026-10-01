"""Persistent project register for the standalone Allshield STEP builder."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from airkan_builder.pricing import rectangular_total_price
from airkan_builder.rules import DEFAULT_PREFIX, RULESET_SHA256, InputError, profile_depth, resolve


PROJECT_SCHEMA = "allshield-airkan-project-v1"
ITEM_ID_PATTERN = re.compile(r"[A-Za-z]{1,3}-[0-9]+")
PREFIX_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_item_id(value):
    item_id = str(value).strip().upper()
    if not ITEM_ID_PATTERN.fullmatch(item_id):
        raise InputError("ID: use a value such as A-10, A-20 or B-10.")
    return item_id


def validate_prefix(value):
    prefix = str(value).strip()
    if not PREFIX_PATTERN.fullmatch(prefix):
        raise InputError("Project prefix: use 1-32 letters, digits, _ or -.")
    if prefix.upper() == "AIRKAN":
        raise InputError("AIRKAN cannot be used as the project prefix.")
    return prefix


def _fingerprint_parameters(parameters):
    identity = dict(parameters)
    if identity.get("family") not in ("CM", "BUY"):
        return identity
    source_value = identity.pop("source_step", "")
    try:
        source = Path(source_value).expanduser().resolve()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        identity["source_step_sha256"] = digest.hexdigest()
    except OSError:
        identity["source_step_unreadable"] = str(source_value)
    return identity


def build_fingerprint(item):
    payload = {
        "id": item["id"],
        "rules_sha256": RULESET_SHA256,
        "connections": item.get("connection_fingerprint", ""),
        "parameters": _fingerprint_parameters(item["parameters"]),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _number(value):
    number = float(value)
    return ("%.3f" % number).rstrip("0").rstrip(".")


def size_text(parameters):
    if parameters.get("family") == "GRILLE_FIRE":
        return parameters["variant"] + " H" + _number(parameters["h_mm"]) + " x B" + _number(parameters["b_mm"]) + " mm"
    if parameters.get("family") == "CM":
        return str(parameters.get("description", "CM"))
    if parameters.get("family") == "BUY":
        return "%s %s | %s x %s mm" % (parameters["supplier"], parameters["article_code"], _number(parameters["a_mm"]), _number(parameters["b_mm"]))
    if "a_mm" in parameters and "b_mm" in parameters:
        value = _number(parameters["a_mm"]) + " x " + _number(parameters["b_mm"])
        if "c_mm" in parameters and "d_mm" in parameters:
            value += " > " + _number(parameters["c_mm"]) + " x " + _number(parameters["d_mm"])
        if "length_mm" in parameters:
            value += " x " + _number(parameters["length_mm"])
        return value + " mm"
    if "diameter_mm" in parameters:
        value = "D" + _number(parameters["diameter_mm"])
        if "length_mm" in parameters:
            value += " x " + _number(parameters["length_mm"])
        return value + " mm"
    if "base_x_mm" in parameters and "base_y_mm" in parameters:
        return _number(parameters["base_x_mm"]) + " x " + _number(parameters["base_y_mm"]) + " mm"
    return "-"


def accepted_price(payload):
    order = payload.get("order") or {}
    value = order.get("unit_price_eur")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return round(float(value), 2)


def accepted_area(payload):
    for container in (payload.get("order") or {}, payload.get("derived") or {}):
        value = container.get("one_sided_price_area_m2")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            continue
        return float(value)
    return None


def _resolved_order(item):
    try:
        return resolve(item["parameters"]).get("order") or {}
    except (InputError, KeyError, TypeError, ValueError):
        return {}


def pricing_values(item):
    order = _resolved_order(item)
    family = item.get("parameters", {}).get("family")
    rate = order.get("area_rate_eur_per_m2")
    if family == "CM":
        rate = item["parameters"].get("area_rate_eur_per_m2")
    area_priced = isinstance(rate, (int, float)) and math.isfinite(rate) and rate >= 0
    override = item.get("area_override_m2")
    manual = isinstance(override, (int, float)) and not isinstance(override, bool) and math.isfinite(override) and override > 0
    area = float(override) if manual else None
    if area is None and item.get("built_fingerprint") == build_fingerprint(item):
        measured = item.get("measured_area_m2")
        if isinstance(measured, (int, float)) and not isinstance(measured, bool) and math.isfinite(measured) and measured > 0:
            area = float(measured)
    if area_priced:
        if area is None:
            total = None
        elif order.get("pricing_model") == "RECTANGULAR_SHEET":
            total = rectangular_total_price(order, area, item.get("measured_nonstandard_frame_count", 0))
        else:
            total = round(area * float(rate), 2)
        return {"area_m2": area, "manual_area": manual, "rate_eur_per_m2": float(rate), "total_eur": total, "status": order.get("pricing_status", "")}
    value = accepted_price({"order": order})
    return {"area_m2": None, "manual_area": False, "rate_eur_per_m2": None, "total_eur": value, "status": order.get("pricing_status", "")}


def _eur(value, suffix=""):
    return "EUR " + format(float(value), ".2f").replace(".", ",") + suffix


def area_text(item):
    pricing = pricing_values(item)
    if pricing["area_m2"] is None:
        return ""
    text = format(pricing["area_m2"], ".3f").replace(".", ",")
    return text + (" *" if pricing["manual_area"] else "")


def rate_text(item):
    pricing = pricing_values(item)
    if pricing["rate_eur_per_m2"] is not None:
        return _eur(pricing["rate_eur_per_m2"], "/m²")
    if pricing["total_eur"] is not None:
        return _eur(pricing["total_eur"], "/st")
    return "On request" if pricing["status"] == "ON_REQUEST" else ""


def total_price_text(item):
    pricing = pricing_values(item)
    if pricing["total_eur"] is not None:
        return _eur(pricing["total_eur"])
    return "On request" if pricing["status"] == "ON_REQUEST" else ""


def price_text(item):
    return total_price_text(item) or rate_text(item)


def output_basename(item, resolved):
    prefix = item["parameters"]["prefix"]
    stem = resolved["filename_stem"]
    suffix = stem[len(prefix) + 1:] if stem.startswith(prefix + "_") else stem
    return prefix + "_" + item["id"] + "_" + suffix


def item_id_from_legacy_prefix(prefix):
    value = str(prefix).strip().upper().replace("_", "-")
    if ITEM_ID_PATTERN.fullmatch(value):
        return value
    match = re.fullmatch(r"([A-Z][A-Z0-9]*?)([0-9]+)", value)
    return match.group(1) + "-" + match.group(2) if match else None


def geometry_fingerprint(item):
    payload = {"rules_sha256": RULESET_SHA256, "parameters": _fingerprint_parameters(item["parameters"])}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rect_port(name, direction, width, height, kind="MATING", external_only=False):
    return {"name": name, "direction": direction, "shape": "RECT", "width_mm": float(width), "height_mm": float(height), "diameter_mm": None, "kind": kind, "external_only": external_only}


def _round_port(name, direction, diameter, kind="MATING"):
    return {"name": name, "direction": direction, "shape": "ROUND", "width_mm": None, "height_mm": None, "diameter_mm": float(diameter), "kind": kind, "external_only": False}


def _reference_port(name, direction, kind, external_only=False):
    return {"name": name, "direction": direction, "shape": None, "width_mm": None, "height_mm": None, "diameter_mm": None, "kind": kind, "external_only": external_only}


def port_specs(parameters):
    """Return the logical connection ports derived from validated build parameters."""
    result = resolve(parameters)
    p = result["params"]
    derived = result["derived"]
    family = p["family"]
    ports = []
    if family == "FRAME":
        ports = [_rect_port("JO_IN", "in", p["a_mm"], p["b_mm"]), _rect_port("JO_DUCT_ENTRY", "out", p["a_mm"], p["b_mm"], "PROFILE_ENTRY_NOT_SEATED_SHEET")]
    elif family in ("BU", "BEND_RECT", "VER", "REG", "SL_RECT"):
        ports = [_rect_port("JO_IN", "in", p["a_mm"], p["b_mm"]), _rect_port("JO_OUT", "out", p["a_mm"], p["b_mm"])]
    elif family == "REDUCER_RECT":
        ports = [_rect_port("JO_IN", "in", p["a_mm"], p["b_mm"]), _rect_port("JO_OUT", "out", p["c_mm"], p["d_mm"])]
    elif family == "RECT_ROUND":
        ports = [_rect_port("JO_IN", "in", p["a_mm"], p["b_mm"]), _round_port("JO_OUT", "out", p["diameter_mm"])]
    elif family == "TEE_RECT":
        ports = [
            _rect_port("JO_IN", "in", p["a_mm"], p["b_mm"]),
            _rect_port("JO_OUT", "out", p["a_mm"], p["b_mm"]),
            _rect_port("JO_BRANCH", "out", p["branch_a_mm"], p["b_mm"]),
        ]
    elif family == "TAKEOFF_RECT":
        free_height = p["length_mm"] - profile_depth(derived["profile"])
        mount_width = p["a_mm"] + 40 if p["variant"] == "P.BI" else p["a_mm"] + (free_height if p["variant"] == "P.45" else 0)
        mount_height = p["b_mm"] + 40 if p["variant"] == "P.BI" else p["b_mm"]
        ports = [_rect_port("JO_MOUNT", "in", mount_width, mount_height, "HOST_CUTOUT"), _rect_port("JO_OUT", "out", p["a_mm"], p["b_mm"])]
    elif family in ("S", "BEND_ROUND", "FLEX_ROUND"):
        ports = [_round_port("JO_IN", "in", p["diameter_mm"]), _round_port("JO_OUT", "out", p["diameter_mm"])]
    elif family == "CONNECTOR_ROUND":
        ports = [_round_port("JO_IN", "in", p["actual_id_mm"]), _round_port("JO_OUT", "out", p["actual_id_mm"])]
    elif family == "FLANGE_ROUND":
        bore = derived["flange"]["bore_mm"]
        ports = [_round_port("JO_IN", "in", bore), _round_port("JO_OUT", "out", bore)]
    elif family == "COVER_ROUND":
        ports = [_round_port("JO_IN", "in", p["actual_od_mm"] - 2 * p["visual_wall_mm"])]
        if p["variant"] == "DFP":
            ports.append(_round_port("JO_DRAIN", "out", p["drain_id_mm"]))
    elif family == "INSPECTION":
        ports = [_reference_port("JO_MOUNT", "in", "MOUNTING_ENVELOPE")]
    elif family == "SUPPORT_PL":
        ports = [_reference_port("JO_MOUNT", "in", "MOUNTING_ENVELOPE")]
    elif family == "HOOD":
        ports = [_round_port("JO_IN", "in", p["diameter_mm"], "ENVELOPE_CONNECTION_NOT_FREE_AIR")]
    elif family == "ROOF":
        ports = [_round_port("JO_DUCT", "in", p["actual_bore_mm"]), _reference_port("JO_ROOF", "out", "ROOF_REFERENCE_ONLY", True)]
    elif family == "GRILLE_FIRE":
        ports = [
            _rect_port("JO_WALL_A", "in", p["b_mm"], p["h_mm"], "PASSIVE_WALL_FACE", True),
            _rect_port("JO_WALL_B", "out", p["b_mm"], p["h_mm"], "PASSIVE_WALL_FACE", True),
        ]
    elif family == "BUY":
        if p["airflow_role"] == "AANZUIG":
            ports = [
                _rect_port("JO_OUTSIDE", "in", p["a_mm"], p["b_mm"], "EXTERNAL_AIR_FACE", True),
                _rect_port("JO_DUCT", "out", p["a_mm"], p["b_mm"], "PURCHASED_DUCT_CONNECTION"),
            ]
        else:
            ports = [
                _rect_port("JO_DUCT", "in", p["a_mm"], p["b_mm"], "PURCHASED_DUCT_CONNECTION"),
                _rect_port("JO_OUTSIDE", "out", p["a_mm"], p["b_mm"], "EXTERNAL_AIR_FACE", True),
            ]
    if not any(port["direction"] == "in" for port in ports):
        ports.append(_reference_port("LOGICAL_FROM", "in", "LOGICAL_PROJECT_RELATION", True))
    if not any(port["direction"] == "out" for port in ports):
        ports.append(_reference_port("LOGICAL_TO", "out", "LOGICAL_PROJECT_RELATION", True))
    return ports


def ports_fit(source_port, target_port, tolerance=0.001):
    if source_port["shape"] is None or target_port["shape"] is None:
        return None
    if source_port["shape"] != target_port["shape"]:
        return False
    if source_port["shape"] == "ROUND":
        return abs(source_port["diameter_mm"] - target_port["diameter_mm"]) <= tolerance
    return abs(source_port["width_mm"] - target_port["width_mm"]) <= tolerance and abs(source_port["height_mm"] - target_port["height_mm"]) <= tolerance


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.project_path = self.root / "project.json"
        self.json_dir = self.root / "json"
        self.step_dir = self.root / "step"
        self.log_dir = self.root / "logs"
        self.staging_dir = self.root / ".staging"
        for directory in (self.root, self.json_dir, self.step_dir, self.log_dir, self.staging_dir):
            directory.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.NamedTemporaryFile(prefix=".allshield_write_", dir=directory):
                    pass
            except OSError as error:
                raise InputError("Project folder is not writable: " + str(directory)) from error
        self.data = self._load_or_create()

    def _load_or_create(self):
        if self.project_path.is_file():
            data = json.loads(self.project_path.read_text(encoding="utf-8"))
            if data.get("schema") != PROJECT_SCHEMA or not isinstance(data.get("items"), list):
                raise InputError("project.json does not use a supported AAVDS project format.")
            data["prefix"] = validate_prefix(data.get("prefix", DEFAULT_PREFIX))
            self.data = data
            changed = self._migrate_pricing_data()
            if "connections" not in data:
                self._migrate_legacy_connections()
                changed = True
            if changed:
                self.save()
            return data
        now = utc_now()
        data = {
            "schema": PROJECT_SCHEMA,
            "version": 2,
            "name": self.root.name,
            "prefix": DEFAULT_PREFIX,
            "created_utc": now,
            "updated_utc": now,
            "items": [],
            "connections": [],
        }
        self.data = data
        self._recover_existing_exports()
        self._migrate_legacy_connections()
        self.save()
        return self.data

    def _recover_existing_exports(self):
        candidates = sorted(self.json_dir.glob("*.json")) + sorted(self.root.glob("*.json"))
        for path in candidates:
            if path == self.project_path:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("schema") != "airkan-component-v3" or not isinstance(payload.get("parameters"), dict):
                continue
            metadata = payload.get("project_item") or {}
            source_prefix = payload["parameters"].get("prefix")
            filename_prefix = path.stem.split("_", 1)[0]
            item_id = metadata.get("id") or item_id_from_legacy_prefix(source_prefix) or item_id_from_legacy_prefix(filename_prefix) or self.next_id()
            try:
                item_id = validate_item_id(item_id)
                resolved = resolve(payload["parameters"])
            except (InputError, KeyError):
                continue
            if any(item["id"] == item_id for item in self.data["items"]):
                continue
            sibling_step = path.with_suffix(".step")
            sibling_fcstd = path.with_suffix(".FCStd")
            item = {
                "id": item_id,
                "from": metadata.get("from", ""),
                "to": metadata.get("to", ""),
                "parameters": resolved["params"],
                "status": "Gebouwd",
                "error": "",
                "updated_utc": payload.get("created_utc", utc_now()),
                "built_fingerprint": "",
                "step_file": str(sibling_step.relative_to(self.root)).replace("\\", "/") if sibling_step.is_file() else "",
                "json_file": str(path.relative_to(self.root)).replace("\\", "/"),
                "legacy_fcstd_file": str(sibling_fcstd.relative_to(self.root)).replace("\\", "/") if sibling_fcstd.is_file() else "",
            }
            area = accepted_area(payload)
            if area is not None:
                item["measured_area_m2"] = area
                item["measured_nonstandard_frame_count"] = int((payload.get("order") or {}).get("requested_nonstandard_frame_count", 0))
            self.data["items"].append(item)
            self.data["items"][-1]["built_fingerprint"] = build_fingerprint(self.data["items"][-1]) if source_prefix else ""
            if not source_prefix or self.data["items"][-1]["parameters"]["prefix"] != self.data["prefix"]:
                self.data["items"][-1]["parameters"]["prefix"] = self.data["prefix"]
                self.data["items"][-1]["status"] = "Gewijzigd"

    def _migrate_pricing_data(self):
        changed = False
        for item in self.data["items"]:
            if "measured_area_m2" not in item and item.get("json_file"):
                try:
                    payload = json.loads(self._managed_path(item["json_file"]).read_text(encoding="utf-8"))
                    area = accepted_area(payload)
                    if area is not None:
                        item["measured_area_m2"] = area
                        item["measured_nonstandard_frame_count"] = int((payload.get("order") or {}).get("requested_nonstandard_frame_count", 0))
                        changed = True
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            for key in ("accepted_unit_price_eur", "accepted_pricing_status"):
                if key in item:
                    item.pop(key)
                    changed = True
        return changed

    def _migrate_legacy_connections(self):
        self.data["version"] = 2
        self.data.setdefault("connections", [])
        item_ids = {item["id"] for item in self.data["items"]}
        used = set()
        for connection in self.data["connections"]:
            for endpoint in (connection["from"], connection["to"]):
                if endpoint.get("kind") == "item":
                    used.add((endpoint["id"], endpoint["port"]))
        for item in self.data["items"]:
            for direction, legacy_key in (("in", "from"), ("out", "to")):
                reference = str(item.pop(legacy_key, "")).strip()
                if not reference:
                    continue
                local = next((port for port in port_specs(item["parameters"]) if port["direction"] == direction and (item["id"], port["name"]) not in used), None)
                if local is None:
                    continue
                local_endpoint = {"kind": "item", "id": item["id"], "port": local["name"]}
                if reference.upper() in item_ids:
                    remote_item = next(candidate for candidate in self.data["items"] if candidate["id"] == reference.upper())
                    remote_direction = "out" if direction == "in" else "in"
                    remote = next((port for port in port_specs(remote_item["parameters"]) if port["direction"] == remote_direction and (remote_item["id"], port["name"]) not in used), None)
                    if remote is None:
                        continue
                    remote_endpoint = {"kind": "item", "id": remote_item["id"], "port": remote["name"]}
                    used.add((remote_item["id"], remote["name"]))
                else:
                    remote_endpoint = {"kind": "external", "id": reference, "port": ""}
                source, target = (remote_endpoint, local_endpoint) if direction == "in" else (local_endpoint, remote_endpoint)
                if not any(connection["from"] == source and connection["to"] == target for connection in self.data["connections"]):
                    self.data["connections"].append({"id": "C-" + uuid.uuid4().hex[:12].upper(), "from": source, "to": target, "fit_override": None})
                    used.add((item["id"], local["name"]))
        self._refresh_connection_fingerprints()

    @property
    def prefix(self):
        return self.data["prefix"]

    @property
    def items(self):
        return sorted(self.data["items"], key=self._sort_key)

    @staticmethod
    def _sort_key(item):
        match = re.fullmatch(r"([A-Z]{1,3})-([0-9]+)", item["id"].upper())
        return (match.group(1), int(match.group(2))) if match else (item["id"], 0)

    def item(self, item_id):
        item_id = validate_item_id(item_id)
        for item in self.data["items"]:
            if item["id"] == item_id:
                return item
        raise InputError("Unknown component: " + item_id)

    def next_id(self, series="A"):
        series = str(series).strip().upper() or "A"
        numbers = []
        for item in self.data.get("items", []):
            match = re.fullmatch(re.escape(series) + r"-([0-9]+)", item["id"], re.IGNORECASE)
            if match:
                numbers.append(int(match.group(1)))
        return series + "-" + str((max(numbers) if numbers else 0) + 10)

    def set_prefix(self, prefix):
        prefix = validate_prefix(prefix)
        if prefix == self.data["prefix"]:
            return False
        self.data["prefix"] = prefix
        for item in self.data["items"]:
            item["parameters"]["prefix"] = prefix
            item["status"] = "Gewijzigd"
            item["error"] = ""
            item["updated_utc"] = utc_now()
        self.save()
        return True

    def save_item(self, item_id, parameters, _legacy_from=None, _legacy_to=None):
        item_id = validate_item_id(item_id)
        parameters = dict(parameters)
        parameters["prefix"] = self.prefix
        resolved = resolve(parameters)
        try:
            item = self.item(item_id)
        except InputError:
            item = {
                "id": item_id,
                "built_fingerprint": "",
                "step_file": "",
                "json_file": "",
                "legacy_fcstd_file": "",
                "connection_fingerprint": "",
            }
            self.data["items"].append(item)
        item.update({
            "parameters": resolved["params"],
            "updated_utc": utc_now(),
            "error": "",
        })
        valid_ports = {port["name"] for port in port_specs(item["parameters"])}
        self.data["connections"] = [
            connection for connection in self.data["connections"]
            if not any(endpoint.get("kind") == "item" and endpoint.get("id") == item_id and endpoint.get("port") not in valid_ports for endpoint in (connection["from"], connection["to"]))
        ]
        self._refresh_connection_fingerprints()
        current = build_fingerprint(item)
        item["status"] = "Gebouwd" if item.get("built_fingerprint") == current else "Gewijzigd"
        self.save()
        return item

    def ports(self, item_id, direction=None):
        ports = port_specs(self.item(item_id)["parameters"])
        return [port for port in ports if direction is None or port["direction"] == direction]

    def port(self, item_id, port_name):
        for port in self.ports(item_id):
            if port["name"] == port_name:
                return port
        raise InputError("Unknown port: " + item_id + ":" + str(port_name))

    def connections_for(self, item_id):
        item_id = validate_item_id(item_id)
        return [connection for connection in self.data["connections"] if any(endpoint.get("kind") == "item" and endpoint.get("id") == item_id for endpoint in (connection["from"], connection["to"]))]

    def connection(self, connection_id):
        for connection in self.data["connections"]:
            if connection["id"] == connection_id:
                return connection
        raise InputError("Unknown connection: " + str(connection_id))

    def _validate_endpoint(self, endpoint, direction):
        kind = endpoint.get("kind")
        if kind == "external":
            name = str(endpoint.get("id", "")).strip()
            if not name:
                raise InputError("The external connection point needs a name.")
            return {"kind": "external", "id": name, "port": ""}
        if kind != "item":
            raise InputError("A connection must refer to a project component or external connection point.")
        item_id = validate_item_id(endpoint.get("id", ""))
        port = self.port(item_id, endpoint.get("port", ""))
        if port["direction"] != direction:
            raise InputError(item_id + ":" + port["name"] + " is not an " + ("output" if direction == "out" else "input") + ".")
        return {"kind": "item", "id": item_id, "port": port["name"]}

    def add_connection(self, source, target):
        source = self._validate_endpoint(source, "out")
        target = self._validate_endpoint(target, "in")
        if source["kind"] == target["kind"] == "external":
            raise InputError("A connection must contain at least one project component.")
        if source["kind"] == target["kind"] == "item" and source["id"] == target["id"]:
            raise InputError("A project component cannot be connected to itself.")
        for endpoint, peer in ((source, target), (target, source)):
            if endpoint["kind"] != "item":
                continue
            port = self.port(endpoint["id"], endpoint["port"])
            if port["external_only"] and peer["kind"] != "external":
                raise InputError(endpoint["id"] + ":" + endpoint["port"] + " can connect only to an external point.")
            for existing in self.data["connections"]:
                if endpoint in (existing["from"], existing["to"]):
                    raise InputError(endpoint["id"] + ":" + endpoint["port"] + " is already connected.")
        connection = {"id": "C-" + uuid.uuid4().hex[:12].upper(), "from": source, "to": target, "fit_override": None}
        self.data["connections"].append(connection)
        self._refresh_connection_fingerprints()
        self.save()
        return connection

    def remove_connection(self, connection_id):
        connection = self.connection(connection_id)
        self.data["connections"].remove(connection)
        self._refresh_connection_fingerprints()
        self.save()

    def _refresh_connection_fingerprints(self):
        for item in self.data["items"]:
            rows = []
            for connection in self.connections_for(item["id"]):
                row = {"from": connection["from"], "to": connection["to"], "geometry": {}}
                for key in ("from", "to"):
                    endpoint = connection[key]
                    if endpoint["kind"] == "item":
                        row["geometry"][key] = geometry_fingerprint(self.item(endpoint["id"]))
                rows.append(row)
            encoded = json.dumps(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True)), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            item["connection_fingerprint"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            if item.get("built_fingerprint") != build_fingerprint(item) and item.get("status") != "Fout":
                item["status"] = "Gewijzigd"

    def connection_payload(self, item_id):
        return [{"id": connection["id"], "from": connection["from"], "to": connection["to"], "fit_override": connection.get("fit_override")} for connection in self.connections_for(item_id)]

    @staticmethod
    def endpoint_text(endpoint):
        if endpoint["kind"] == "external":
            return "EXT:" + endpoint["id"]
        return endpoint["id"] + ":" + endpoint["port"]

    def connection_summary(self, item_id, direction):
        values = []
        for connection in self.connections_for(item_id):
            local_key = "to" if direction == "in" else "from"
            remote_key = "from" if direction == "in" else "to"
            if connection[local_key].get("kind") == "item" and connection[local_key].get("id") == item_id:
                values.append(self.endpoint_text(connection[remote_key]))
        return "; ".join(values)

    def _override_valid(self, connection):
        override = connection.get("fit_override")
        if not override or connection["from"]["kind"] != "item" or connection["to"]["kind"] != "item":
            return False
        return (override.get("from_geometry_sha256") == geometry_fingerprint(self.item(connection["from"]["id"])) and
                override.get("to_geometry_sha256") == geometry_fingerprint(self.item(connection["to"]["id"])))

    def connection_fit(self, connection):
        if connection["from"]["kind"] != "item" or connection["to"]["kind"] != "item":
            return True
        source_port = self.port(connection["from"]["id"], connection["from"]["port"])
        target_port = self.port(connection["to"]["id"], connection["to"]["port"])
        return ports_fit(source_port, target_port)

    def connection_issues(self, item_id):
        item_id = validate_item_id(item_id)
        issues = []
        connected_ports = set()
        for connection in self.connections_for(item_id):
            for endpoint in (connection["from"], connection["to"]):
                if endpoint.get("kind") == "item" and endpoint.get("id") == item_id:
                    connected_ports.add(endpoint["port"])
            fit = self.connection_fit(connection)
            if fit is False:
                is_source = connection["from"].get("kind") == "item" and connection["from"].get("id") == item_id
                code = "NEXT PIECE DOES NOT FIT" if is_source else "PRECEDING PIECE DOES NOT FIT"
                peer = connection["to"] if is_source else connection["from"]
                accepted = self._override_valid(connection)
                issues.append({"code": "MANUALLY ACCEPTED" if accepted else code, "message": ("MANUALLY ACCEPTED: " if accepted else code + ": ") + self.endpoint_text(peer), "connection_id": connection["id"], "overrideable": not accepted, "accepted": accepted})
        for port in self.ports(item_id):
            if port["name"] not in connected_ports:
                code = "NO PRECEDING PIECE" if port["direction"] == "in" else "NO NEXT PIECE"
                issues.append({"code": code, "message": code + ": " + port["name"], "connection_id": None, "overrideable": False, "accepted": False})
        return issues

    def error_text(self, item_id):
        try:
            messages = [issue["message"] for issue in self.connection_issues(item_id) if not issue["accepted"]]
        except InputError as error:
            messages = [str(error)]
        build_error = str(self.item(item_id).get("error", "")).strip()
        if build_error:
            messages.append(build_error)
        return " | ".join(messages)

    def accept_fit_override(self, connection_id):
        connection = self.connection(connection_id)
        if connection["from"]["kind"] != "item" or connection["to"]["kind"] != "item" or self.connection_fit(connection) is not False:
            raise InputError("Only a current fit mismatch can be accepted manually.")
        connection["fit_override"] = {
            "accepted_utc": utc_now(),
            "from_geometry_sha256": geometry_fingerprint(self.item(connection["from"]["id"])),
            "to_geometry_sha256": geometry_fingerprint(self.item(connection["to"]["id"])),
        }
        self.save()
        return connection

    def set_error(self, item_id, message):
        item = self.item(item_id)
        item["error"] = str(message).strip()
        item["status"] = "Fout" if item["error"] else item.get("status", "Gewijzigd")
        item["updated_utc"] = utc_now()
        self.save()

    def set_area_override(self, item_id, area_m2):
        item = self.item(item_id)
        if pricing_values(item)["rate_eur_per_m2"] is None:
            raise InputError("This component does not have area-based pricing.")
        if area_m2 is None:
            item.pop("area_override_m2", None)
        else:
            try:
                area = float(area_m2)
            except (TypeError, ValueError) as error:
                raise InputError("Area: enter a number in m².") from error
            if not math.isfinite(area) or area <= 0:
                raise InputError("Area must be greater than 0 m².")
            item["area_override_m2"] = area
        item["updated_utc"] = utc_now()
        self.save()
        return item

    def dirty_items(self):
        return [item for item in self.items if build_fingerprint(item) != item.get("built_fingerprint")]

    def old_artifacts(self, item_ids):
        paths = []
        for item_id in item_ids:
            item = self.item(item_id)
            for key in ("step_file", "json_file", "legacy_fcstd_file"):
                if item.get(key):
                    path = self._managed_path(item[key])
                    if path.is_file():
                        paths.append(path)
        return paths

    def commit_build(self, item_id, staged_step, staged_json):
        item = self.item(item_id)
        staged_step = Path(staged_step).resolve()
        staged_json = Path(staged_json).resolve()
        if not staged_step.is_file() or not staged_json.is_file():
            raise InputError("Temporary STEP or JSON output is missing.")
        if staged_step.stat().st_size == 0 or staged_json.stat().st_size == 0:
            raise InputError("Temporary STEP or JSON output is empty.")
        payload = json.loads(staged_json.read_text(encoding="utf-8"))
        if payload.get("schema") != "airkan-component-v3":
            raise InputError("The FreeCAD worker did not return Airkan component JSON.")
        metadata = payload.get("project_item") or {}
        if metadata.get("id") != item["id"]:
            raise InputError("The FreeCAD worker returned output for a different component.")
        if metadata.get("build_fingerprint") and metadata["build_fingerprint"] != build_fingerprint(item):
            raise InputError("The component or its connections changed during the build; the result was not accepted.")
        area = accepted_area(payload)
        if area is not None:
            for key in ("base_sheet_price_eur", "requested_nonstandard_frame_surcharge_eur", "airtightness_surcharge_eur", "unit_price_eur"):
                (payload.get("order") or {}).pop(key, None)
                (payload.get("derived") or {}).pop(key, None)
            (payload.get("bom") or {}).pop("unit_price_eur", None)
        destination_step = self.step_dir / staged_step.name
        destination_json = self.json_dir / (item["id"] + ".json")
        payload["files"] = {
            "step": str(destination_step),
            "parameters": str(destination_json),
        }
        json_temp = destination_json.with_suffix(".json.tmp")
        json_temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        old_paths = [self._managed_path(item[key]) for key in ("step_file", "json_file", "legacy_fcstd_file") if item.get(key)]
        os.replace(staged_step, destination_step)
        os.replace(json_temp, destination_json)
        item.update({
            "step_file": str(destination_step.relative_to(self.root)).replace("\\", "/"),
            "json_file": str(destination_json.relative_to(self.root)).replace("\\", "/"),
            "legacy_fcstd_file": "",
            "built_fingerprint": build_fingerprint(item),
            "status": "Gebouwd",
            "error": "",
            "built_utc": utc_now(),
            "updated_utc": utc_now(),
        })
        item.pop("accepted_unit_price_eur", None)
        item.pop("accepted_pricing_status", None)
        if area is None:
            item.pop("measured_area_m2", None)
            item.pop("measured_nonstandard_frame_count", None)
        else:
            item["measured_area_m2"] = area
            item["measured_nonstandard_frame_count"] = int((payload.get("order") or {}).get("requested_nonstandard_frame_count", 0))
        self.save()
        active_paths = {destination_step, destination_json}
        for old_path in old_paths:
            if old_path not in active_paths and old_path.is_file():
                old_path.unlink()
        return item

    def remove_item(self, item_id):
        item = self.item(item_id)
        for key in ("step_file", "json_file", "legacy_fcstd_file"):
            if item.get(key):
                path = self._managed_path(item[key])
                if path.is_file():
                    path.unlink()
        self.data["connections"] = [connection for connection in self.data["connections"] if all(endpoint.get("kind") != "item" or endpoint.get("id") != item["id"] for endpoint in (connection["from"], connection["to"]))]
        self.data["items"].remove(item)
        self._refresh_connection_fingerprints()
        self.save()

    def _managed_path(self, relative):
        if Path(relative).is_absolute():
            raise InputError("Absoluut bestandspad is niet toegestaan in het projectregister.")
        path = (self.root / relative).resolve()
        if self.root not in path.parents:
            raise InputError("Onveilig bestandspad in projectregister.")
        return path

    def save(self):
        self.data["updated_utc"] = utc_now()
        temporary = self.project_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, self.project_path)
