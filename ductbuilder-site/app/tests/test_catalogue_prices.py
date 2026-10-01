import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRICES = json.loads((ROOT / "airkan_builder" / "catalogue_prices_v1.json").read_text(encoding="utf-8"))
RULES = json.loads((ROOT / "airkan_builder" / "catalogue_rules_v3.json").read_text(encoding="utf-8"))


class CataloguePriceTests(unittest.TestCase):
    def test_every_builder_family_has_a_price_model(self):
        families = {family["id"] for family in RULES["families"]}
        self.assertEqual(set(PRICES["family_models"]), families)

    def test_rectangular_material_thickness_grid_is_complete(self):
        grid = PRICES["rectangular_sheet_eur_per_m2"]
        self.assertEqual(grid["thickness_mm"], [0.75, 0.95, 1.2, 1.5])
        self.assertEqual(set(grid["rows"]), {"GALVA", "ALMG3", "INOX304", "INOX316"})
        self.assertTrue(all(len(row) == 4 for material in grid["rows"].values() for row in material.values()))
        self.assertEqual(grid["rows"]["GALVA"]["STRAIGHT_STANDARD"][1], 43.03)
        self.assertEqual(grid["rows"]["INOX316"]["RECT_TO_ROUND"][1], 218.58)
        self.assertEqual(grid["standard_straight_lengths_mm"]["TDC20"], [916, 1166, 1416])
        self.assertEqual(grid["standard_straight_lengths_mm"]["TDC30"], [892, 1142, 1392])
        self.assertEqual(grid["finished_to_net_plate_deduction_mm"], {"TDC20": 84, "TDC30": 108})
        self.assertEqual(grid["base_frame_by_maximum_side_mm"]["A40_minimum_inclusive"], 2000)

    def test_loose_frames_are_separate_components(self):
        frames = PRICES["loose_rectangular_frame_components"]
        self.assertEqual(frames["profiles_eur_per_m"]["E30"]["GALVA"], 3.66)
        self.assertEqual(frames["corners_eur_each"]["H40"]["GALVA"], 2.48)
        self.assertEqual(frames["profile_to_corner"]["A40"], "H40")

    def test_round_source_grids_have_all_catalogue_rows(self):
        self.assertEqual(len(PRICES["round_spiral_eur_per_m"]["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(PRICES["round_segment_bend_eur_each"]["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(PRICES["round_flange_eur_each"]["rows_by_diameter_mm"]), 27)
        self.assertEqual(PRICES["round_spiral_eur_per_m"]["rows_by_diameter_mm"]["900"][5], 94.27)
        self.assertEqual(PRICES["round_segment_bend_eur_each"]["rows_by_diameter_mm"]["900"][0], 353.68)
        self.assertEqual(PRICES["round_flange_eur_each"]["rows_by_diameter_mm"]["1500"][0], 226.31)

    def test_register_grid_is_complete(self):
        grid = PRICES["register_eur_each"]
        self.assertEqual(len(grid["h_mm"]), 11)
        self.assertEqual(len(grid["rows_by_b_mm"]), 11)
        self.assertTrue(all(len(row) == 11 for row in grid["rows_by_b_mm"].values()))
        self.assertEqual(grid["rows_by_b_mm"]["1000"][8], 394.22)
        self.assertEqual(grid["REGH_supplement_eur_each"], 14.85)

    def test_round_accessory_grids_exclude_package_quantities(self):
        flex = PRICES["round_flexible_sleeve_eur_each"]
        connector = PRICES["round_connector_eur_each"]
        cover = PRICES["round_cover_eur_each"]
        self.assertEqual(len(flex["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(connector["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(cover["rows_by_diameter_mm"]), 27)
        self.assertEqual(connector["rows_by_diameter_mm"]["80"], [1.40, 1.47, 2.39, None])
        self.assertEqual(connector["rows_by_diameter_mm"]["1500"], [54.17, 54.17, None, 88.59])
        self.assertEqual(flex["rows_by_diameter_mm"]["900"][2], 304.29)
        self.assertEqual(cover["rows_by_diameter_mm"]["1000"][4], 94.28)

    def test_roof_and_support_grids_are_complete(self):
        hood = PRICES["round_hood_eur_each"]
        roof = PRICES["round_roof_passage_eur_each"]
        support = PRICES["support_eur_each"]
        self.assertEqual(len(hood["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(roof["rows_by_diameter_mm"]), 27)
        self.assertEqual(len(support["rows_by_diameter_mm"]), 27)
        self.assertEqual(hood["rows_by_diameter_mm"]["1500"][4], 2746.63)
        self.assertEqual(roof["rows_by_diameter_mm"]["80"], [20.58, 17.35, 69.40, 52.05, 34.70, 34.70])
        self.assertEqual(support["fixed"]["PL300"], 7.98)
        self.assertEqual(support["rows_by_diameter_mm"]["1120"][2], None)

    def test_inspection_grids_preserve_material_variants(self):
        inspection = PRICES["inspection_hatch_eur_each"]
        self.assertEqual(inspection["ISK"]["600x500"]["INOX304"], 285.87)
        self.assertEqual(inspection["ISR"]["660x510"]["GALVA"], 127.02)
        self.assertEqual(inspection["mounting_eur_each"], 7.50)

    def test_round_branch_matrices_are_complete(self):
        grids = PRICES["round_branch_eur_each"]
        self.assertEqual(len(grids["branch_diameter_groups_mm"]), 12)
        self.assertEqual(len(grids["AP"]), 27)
        self.assertEqual(len(grids["APA"]), 27)
        self.assertEqual(len(grids["PSA"]), 26)
        self.assertTrue(all(len(row) == 12 for variant in ("AP", "APA", "PSA") for row in grids[variant].values()))
        self.assertEqual(grids["AP"]["1500"][11], 1601.60)
        self.assertEqual(grids["APA"]["900"][9], 697.51)
        self.assertEqual(grids["PSA"]["100"][0], 7.09)
        self.assertIsNone(grids["PSA"]["1400"][11])

    def test_rectangular_branch_to_round_has_four_full_grids(self):
        grid = PRICES["rectangular_branch_to_round_eur_each"]
        for key in ("PR_B_LT_DIAMETER", "PR_B_GT_DIAMETER", "PRA_B_LT_DIAMETER", "PRA_B_GT_DIAMETER"):
            self.assertEqual(len(grid[key]), 7)
            self.assertTrue(all(len(row) == 3 for row in grid[key]))
        self.assertEqual(grid["PR_B_LT_DIAMETER"][0], [31.23, 39.37, 50.99])
        self.assertEqual(grid["PRA_B_GT_DIAMETER"][-1][-1], 357.99)

    def test_no_family_is_left_with_a_pending_grid(self):
        pending = {family: model for family, model in PRICES["family_models"].items() if model["model"] == "PENDING_SOURCE_GRID"}
        self.assertEqual(pending, {})


if __name__ == "__main__":
    unittest.main()