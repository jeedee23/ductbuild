"""Pure Airkan catalogue price lookup; no CAD imports or geometry assumptions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRICE_PATH = Path(__file__).with_name("catalogue_prices_v1.json")
PRICES = json.loads(PRICE_PATH.read_text(encoding="utf-8"))
PRICESET_SHA256 = hashlib.sha256(PRICE_PATH.read_bytes()).hexdigest()


def rectangular_priced_thicknesses(family, material):
    family_model = PRICES["family_models"].get(family, {})
    if family_model.get("model") != "RECTANGULAR_SHEET":
        return ()
    grid = PRICES["rectangular_sheet_eur_per_m2"]
    categories = grid["rows"].get(material, {})
    return tuple(
        float(thickness)
        for index, thickness in enumerate(grid["thickness_mm"])
        if categories and all(prices[index] is not None for prices in categories.values())
    )


def _key(value):
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _index(values, value):
    number = float(value)
    for index, candidate in enumerate(values):
        if abs(float(candidate) - number) < 1e-9:
            return index
    return None


def _grid_price(grid_name, row_key, column_name, variants_key="variants"):
    grid = PRICES[grid_name]
    row = grid["rows_by_diameter_mm"].get(_key(row_key))
    index = grid[variants_key].index(column_name) if column_name in grid[variants_key] else None
    return None if row is None or index is None else row[index]


def _result(model, price=None, status="CATALOGUE_PRICE", **details):
    result = {
        "pricing_model": model,
        "pricing_status": status,
        "currency": "EUR",
        "price_catalogue_date": PRICES["catalogue_date"],
        "price_rules_sha256": PRICESET_SHA256,
    }
    if price is not None:
        result["unit_price_eur"] = round(float(price), 2)
    result.update(details)
    return result


def _unavailable(model, reason="The catalogue combination has no price."):
    return _result(model, status="ON_REQUEST", pricing_note=reason)


def _rectangular_rate(parameters, derived, family_model):
    grid = PRICES["rectangular_sheet_eur_per_m2"]
    category = family_model["category"]
    base_frame = None
    if category == "STRAIGHT_LENGTH_RULE":
        standard = grid["standard_straight_lengths_mm"]
        finished_length = float(parameters["length_mm"])
        if parameters.get("length_basis") == "PROFIELINVOER":
            finished_length += 2.0 * {"E30": 27.0, "A40": 36.0, "GEEN": 0.0}[derived["profile"]]
        thickness = float(derived["t_mm"])
        material = parameters["material"]
        maximum_side = max(float(parameters["a_mm"]), float(parameters["b_mm"]))
        frame_ranges = grid["base_frame_by_maximum_side_mm"]
        if maximum_side <= frame_ranges["TDC20_maximum_inclusive"]:
            base_frame = "TDC20"
        elif maximum_side < frame_ranges["TDC30_maximum_exclusive"]:
            base_frame = "TDC30"
        else:
            base_frame = "A40"
        valid_lengths = standard.get(base_frame, [])
        deduction = grid["finished_to_net_plate_deduction_mm"].get(base_frame, 0.0)
        source_net_plate_length = finished_length - deduction
        if material != "GALVA" and thickness > 0.9:
            valid_lengths = standard["non_galva_above_0_9_mm"]
        category = "STRAIGHT_STANDARD" if any(abs(source_net_plate_length - value) < 1e-9 for value in valid_lengths) else grid["outside_standard_length_category"]
    thickness_index = _index(grid["thickness_mm"], derived["t_mm"])
    material_rows = grid["rows"].get(parameters["material"])
    rate = None if material_rows is None or thickness_index is None else material_rows[category][thickness_index]
    if rate is None:
        return _unavailable("RECTANGULAR_SHEET", "The material/sheet-thickness/category combination has no catalogue rate.")
    result = _result(
        "RECTANGULAR_SHEET",
        status="PENDING_GEOMETRY_MEASUREMENT",
        price_basis="AIRKAN_CATALOGUE_EUR_PER_M2",
        price_category=category,
        area_rate_eur_per_m2=rate,
        area_method="PHYSICAL_SHEET_ALL_FACES_DIVIDED_BY_TWO; frame solids excluded",
        included_frame_basis="Source base frame (TDC20, TDC30 or A40 by maximum side) is included in the sheet rate",
        requested_nonstandard_frame_surcharge_percent_each=grid["surcharges"]["requested_nonstandard_frame_percent_per_frame"],
        airtightness_surcharge_percent=grid["surcharges"]["airtightness_class_C_percent"] if parameters.get("airtightness_class") == "C" else 0.0,
    )
    if base_frame is not None:
        result["base_frame_profile"] = base_frame
        result["finished_length_mm"] = finished_length
        result["source_net_plate_length_mm"] = source_net_plate_length
    return result


def price_for_parameters(parameters, derived):
    family = parameters["family"]
    family_model = PRICES["family_models"][family]
    model = family_model["model"]
    if model == "PURCHASED_ITEM":
        result = {
            "pricing_model": model,
            "pricing_status": parameters["price_status"],
            "currency": "EUR",
            "price_source": parameters["price_source"],
        }
        if parameters["price_status"] == "BEVESTIGD":
            result["unit_price_eur"] = round(float(parameters["unit_price_eur"]), 2)
        return result
    if model == "RECTANGULAR_SHEET":
        return _rectangular_rate(parameters, derived, family_model)
    if model == "LOOSE_RECTANGULAR_FRAME":
        frames = PRICES["loose_rectangular_frame_components"]
        profile = derived["profile"]
        corner = frames["profile_to_corner"][profile]
        material = parameters["material"]
        profile_rate = frames["profiles_eur_per_m"][profile].get(material)
        corner_price = frames["corners_eur_each"][corner].get(material)
        if profile_rate is None or corner_price is None:
            return _unavailable(model)
        perimeter_m = 2.0 * (parameters["a_mm"] + parameters["b_mm"]) / 1000.0
        price = perimeter_m * profile_rate + 4.0 * corner_price
        return _result(model, price, price_basis="PROFILE_EUR_PER_M_PLUS_FOUR_CORNERS", profile=profile, corner=corner,
                       profile_length_m=perimeter_m, profile_rate_eur_per_m=profile_rate, corner_eur_each=corner_price)
    if model == "ROUND_SPIRAL":
        grid = PRICES["round_spiral_eur_per_m"]
        row = grid["rows_by_diameter_mm"].get(_key(parameters["diameter_mm"]))
        index = _index(grid["thickness_mm"], derived["t_mm"])
        rate = None if row is None or index is None else row[index]
        if rate is None:
            return _unavailable(model)
        length_m = parameters["length_mm"] / 1000.0
        return _result(model, rate * length_m, price_basis="AIRKAN_CATALOGUE_EUR_PER_M", length_m=length_m,
                       rate_eur_per_m=rate, cut_cost_status="EXCLUDED; number of cuts is not a builder parameter")
    if model == "ROUND_SEGMENT_BEND":
        price = _grid_price("round_segment_bend_eur_each", parameters["diameter_mm"], parameters["variant"])
    elif model == "REGISTER_GRID":
        grid = PRICES["register_eur_each"]
        h_index = _index(grid["h_mm"], parameters["b_mm"])
        row = grid["rows_by_b_mm"].get(_key(parameters["a_mm"]))
        price = None if row is None or h_index is None else row[h_index]
        if price is not None and parameters["variant"] == "REGH":
            price += grid["REGH_supplement_eur_each"]
    elif model == "ROUND_FLEXIBLE_SLEEVE":
        price = _grid_price("round_flexible_sleeve_eur_each", parameters["diameter_mm"], parameters["variant"])
    elif model == "ROUND_CONNECTOR":
        variant = "VL_OR_VLB" if parameters["variant"] in ("VL", "VLB") else parameters["variant"]
        price = _grid_price("round_connector_eur_each", parameters["diameter_mm"], variant)
    elif model == "ROUND_FLANGE":
        price = _grid_price("round_flange_eur_each", parameters["diameter_mm"], parameters["material"], "materials")
    elif model == "ROUND_COVER":
        variant = "DG_OR_DFG" if parameters["variant"] in ("DG", "DFG") else parameters["variant"]
        price = _grid_price("round_cover_eur_each", parameters["diameter_mm"], variant)
    elif model == "ROUND_HOOD":
        price = _grid_price("round_hood_eur_each", parameters["diameter_mm"], parameters["variant"])
    elif model == "ROUND_ROOF_PASSAGE":
        price = _grid_price("round_roof_passage_eur_each", parameters["diameter_mm"], parameters["variant"])
    elif model == "INSPECTION_HATCH":
        grid = PRICES["inspection_hatch_eur_each"]
        variant = parameters["variant"]
        if variant == "IS235":
            price = grid[variant]["GALVA"]
        else:
            size = _key(parameters["size_a_mm"]) + "x" + _key(parameters["size_b_mm"])
            price = grid[variant].get(size, {}).get("GALVA")
    elif model == "SUPPORT_FIXED":
        price = PRICES["support_eur_each"]["fixed"].get(parameters["variant"])
    elif model in ("EXISTING_RULESET_GRID", "USER_RATE"):
        return {}
    elif model == "ON_REQUEST":
        return _unavailable(model)
    else:
        return _unavailable(model, "Prijsmodel is alleen als bronmatrix vastgelegd; familie is nog niet bouwbaar.")
    return _unavailable(model) if price is None else _result(model, price, price_basis="AIRKAN_CATALOGUE_EUR_EACH")


def rectangular_total_price(order, area_m2, nonstandard_frame_count=0):
    base_price = float(area_m2) * order["area_rate_eur_per_m2"]
    frame_surcharge = base_price * order["requested_nonstandard_frame_surcharge_percent_each"] * int(nonstandard_frame_count) / 100.0
    airtightness_surcharge = base_price * order["airtightness_surcharge_percent"] / 100.0
    return round(base_price + frame_surcharge + airtightness_surcharge, 2)


def complete_rectangular_geometry_price(order, sheet_all_faces_area_mm2, nonstandard_frame_count):
    if order.get("pricing_status") != "PENDING_GEOMETRY_MEASUREMENT":
        return {}
    area_m2 = float(sheet_all_faces_area_mm2) / 1_000_000.0 / 2.0
    return {
        "pricing_status": "AREA_MEASURED",
        "sheet_all_faces_area_mm2": float(sheet_all_faces_area_mm2),
        "one_sided_price_area_m2": area_m2,
        "included_frame_basis": "Source base frame (TDC20, TDC30 or A40 by maximum side) included in base sheet rate",
        "requested_nonstandard_frame_count": int(nonstandard_frame_count),
        "calculation": "Total is calculated on demand from area, current rate, frame count and airtightness surcharge.",
    }


def nonstandard_frame_surcharge_count(frames):
    minimum_a40_side = PRICES["rectangular_sheet_eur_per_m2"]["base_frame_by_maximum_side_mm"]["A40_minimum_inclusive"]
    return sum(1 for frame in frames if max(float(value) for value in frame["inside_mm"]) < minimum_a40_side)