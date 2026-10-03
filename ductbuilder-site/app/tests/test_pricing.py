from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from airkan_builder.rules import defaults, resolve
from airkan_builder.pricing import complete_rectangular_geometry_price, nonstandard_frame_surcharge_count, rectangular_priced_thicknesses, rectangular_total_price


def priced(family, **changes):
    parameters = defaults(family)
    parameters.update(changes)
    return resolve(parameters)["order"]


class PricingTests(unittest.TestCase):
    def test_rectangular_thickness_options_only_include_priced_source_cells(self):
        self.assertEqual(rectangular_priced_thicknesses("BU", "GALVA"), (0.75, 0.95, 1.2, 1.5))
        self.assertEqual(rectangular_priced_thicknesses("BEND_RECT", "ALMG3"), (0.75, 0.95, 1.2))
        self.assertEqual(rectangular_priced_thicknesses("RECT_ROUND", "INOX304"), (0.75, 0.95))
        self.assertEqual(rectangular_priced_thicknesses("TEE_RECT", "INOX316"), (0.75, 0.95))
        self.assertEqual(rectangular_priced_thicknesses("S", "GALVA"), ())

    def test_loose_frames_use_profile_and_four_corners(self):
        order = priced("FRAME", a_mm=1000, b_mm=800, material="GALVA")
        self.assertEqual(order["profile"], "E30")
        self.assertEqual(order["corner"], "H30")
        self.assertEqual(order["unit_price_eur"], 16.10)

    def test_spiral_price_uses_catalogue_thickness_and_length(self):
        order = priced("S", diameter_mm=900, length_mm=4200)
        self.assertEqual(order["rate_eur_per_m"], 94.27)
        self.assertEqual(order["unit_price_eur"], 395.93)
        self.assertIn("EXCLUDED", order["cut_cost_status"])

    def test_exact_piece_grids(self):
        cases = [
            ("BEND_ROUND", {"diameter_mm": 900, "variant": "BS9X", "t_mm": 1.0}, 353.68),
            ("REG", {"a_mm": 1000, "b_mm": 800, "variant": "REGH"}, 333.99),
            ("FLANGE_ROUND", {"diameter_mm": 900, "material": "GALVA"}, 92.94),
            ("FLEX_ROUND", {"diameter_mm": 500, "variant": "SM", "length_mm": 100, "outer_diameter_mm": 510}, 137.80),
            ("CONNECTOR_ROUND", {"diameter_mm": 500, "variant": "VT", "length_mm": 100, "actual_id_mm": 500, "actual_od_mm": 502}, 13.80),
            ("COVER_ROUND", {"diameter_mm": 1000, "variant": "DFP", "length_mm": 50, "actual_od_mm": 1002, "drain_id_mm": 10, "drain_od_mm": 12, "drain_length_mm": 20}, 94.28),
            ("HOOD", {"diameter_mm": 1500, "variant": "KRS", "outer_diameter_mm": 1600, "length_mm": 500}, 2746.63),
            ("ROOF", {"diameter_mm": 80, "variant": "DD60", "base_x_mm": 407, "base_y_mm": 407, "length_mm": 500, "actual_bore_mm": 80}, 69.40),
            ("INSPECTION", {"variant": "ISR", "size_a_mm": 660, "size_b_mm": 510}, 127.02),
            ("SUPPORT_PL", {"variant": "PL300"}, 7.98),
            ("AP_APA_PSA", {"variant": "AP", "d1_mm": 300, "d2_mm": 150}, 38.42),
            ("AP_APA_PSA", {"variant": "APA", "d1_mm": 300, "d2_mm": 150}, 46.96),
            ("AP_APA_PSA", {"variant": "PSA", "d1_mm": 100, "d2_mm": 80}, 7.09),
            ("PR_PRA", {"d1_mm": 200, "b_mm": 100, "l_mm": 200, "position": "S"}, 31.23),
            ("PR_PRA", {"d1_mm": 200, "b_mm": 100, "l_mm": 200, "position": "A"}, 43.72),
            ("PR_PRA", {"d1_mm": 300, "b_mm": 150, "l_mm": 200, "position": "S", "frame_profile": "E20"}, 39.37),
        ]
        for family, changes, expected in cases:
            with self.subTest(family=family):
                self.assertEqual(priced(family, **changes)["unit_price_eur"], expected)

    def test_nonstandard_bu_uses_fitting_rate_and_waits_for_area(self):
        order = priced("BU", t_mm=0.95, length_mm=1100)
        self.assertEqual(order["pricing_status"], "PENDING_GEOMETRY_MEASUREMENT")
        self.assertEqual(order["price_category"], "FITTING_OR_SHORT")
        self.assertEqual(order["area_rate_eur_per_m2"], 56.70)
        self.assertNotIn("unit_price_eur", order)

    def test_standard_bu_uses_straight_rate(self):
        order = priced("BU", t_mm=0.95, length_mm=1250)
        self.assertEqual(order["price_category"], "STRAIGHT_STANDARD")
        self.assertEqual(order["base_frame_profile"], "TDC20")
        self.assertEqual(order["area_rate_eur_per_m2"], 43.03)
        self.assertEqual(order["source_net_plate_length_mm"], 1166)

        tdc20_mismatch = priced("BU", t_mm=0.95, a_mm=1000, b_mm=800, length_mm=1226)
        tdc30_match = priced("BU", t_mm=0.95, a_mm=1300, b_mm=800, length_mm=1250)
        self.assertEqual(tdc20_mismatch["price_category"], "FITTING_OR_SHORT")
        self.assertEqual(tdc30_match["price_category"], "STRAIGHT_STANDARD")
        self.assertEqual(tdc30_match["base_frame_profile"], "TDC30")

        project = priced("BU", t_mm=1.2, a_mm=1640, b_mm=1020, length_mm=1500)
        self.assertEqual(project["source_net_plate_length_mm"], 1392)
        self.assertEqual(project["price_category"], "STRAIGHT_STANDARD")
        self.assertEqual(project["area_rate_eur_per_m2"], 56.24)

    def test_manual_and_automatic_bu_both_use_catalogue_area_prices(self):
        automatic = priced("BU", a_mm=1640, b_mm=1020, length_mm=1500, thickness_mode="AIRKAN_BC")
        manual = priced("BU", a_mm=1640, b_mm=1020, length_mm=1500, t_mm=1.5)
        self.assertEqual(automatic["pricing_status"], "PENDING_GEOMETRY_MEASUREMENT")
        self.assertEqual(automatic["area_rate_eur_per_m2"], 56.24)
        self.assertEqual(manual["pricing_status"], "PENDING_GEOMETRY_MEASUREMENT")
        self.assertEqual(manual["area_rate_eur_per_m2"], 67.05)

    def test_catalogue_dash_becomes_on_request(self):
        order = priced("FLANGE_ROUND", diameter_mm=1500, material="INOX304")
        self.assertEqual(order["pricing_status"], "ON_REQUEST")
        self.assertNotIn("unit_price_eur", order)

    def test_round_branch_price_matrix_rejects_nonstandard_diameters(self):
        order = priced("AP_APA_PSA", variant="AP", d1_mm=301, d2_mm=150)
        self.assertEqual(order["pricing_status"], "ON_REQUEST")
        self.assertIn("listed nominal", order["pricing_note"])

    def test_pr_pra_partial_position_remains_on_request(self):
        order = priced("PR_PRA", d1_mm=200, b_mm=100, l_mm=200, position="P", offset_mm=10)
        self.assertEqual(order["pricing_status"], "ON_REQUEST")
        self.assertIn("intermediate P", order["pricing_note"])

    def test_rectangular_geometry_stores_inputs_and_calculates_total_on_demand(self):
        order = priced("BU", t_mm=0.95, length_mm=1100, airtightness_class="C")
        completed = complete_rectangular_geometry_price(order, sheet_all_faces_area_mm2=7_200_000, nonstandard_frame_count=2)
        self.assertEqual(completed["one_sided_price_area_m2"], 3.6)
        self.assertEqual(completed["requested_nonstandard_frame_count"], 2)
        self.assertNotIn("unit_price_eur", completed)
        self.assertEqual(rectangular_total_price(order, completed["one_sided_price_area_m2"], completed["requested_nonstandard_frame_count"]), 224.53)
        self.assertEqual(nonstandard_frame_surcharge_count([{"inside_mm": [1000, 800]}, {"inside_mm": [2000, 800]}]), 1)


if __name__ == "__main__":
    unittest.main()