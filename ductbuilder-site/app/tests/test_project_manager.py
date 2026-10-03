"""Pure tests for the standalone project register."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from airkan_builder.rules import defaults
from allshield_project import ProjectStore, area_text, build_fingerprint, item_id_from_legacy_prefix, output_basename, port_specs, price_text, rate_text, size_text, total_price_text, validate_item_id


class ProjectStoreTests(unittest.TestCase):
    def valid_bu(self):
        return dict(defaults("BU"), t_mm=0.95)

    def test_numbering_and_dirty_tracking(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            self.assertEqual(store.next_id(), "A-10")
            item = store.save_item("a-10", self.valid_bu())
            self.assertEqual(item["id"], "A-10")
            self.assertEqual(store.next_id(), "A-20")
            self.assertEqual([row["id"] for row in store.dirty_items()], ["A-10"])

    def test_direct_catalogue_piece_price_is_visible_before_build(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", dict(defaults("REG"), a_mm=1000, b_mm=800, variant="REGH"))
            self.assertEqual(item["status"], "Gewijzigd")
            self.assertEqual(price_text(item), "EUR 333,99")

            on_request = store.save_item("A-20", dict(defaults("FLANGE_ROUND"), diameter_mm=1500, material="INOX304"))
            self.assertEqual(price_text(on_request), "On request")

            promoted = store.save_item("A-25", defaults("AP_APA_PSA"))
            self.assertEqual(price_text(promoted), "EUR 38,42")

            pr = store.save_item("A-27", dict(defaults("PR_PRA"), d1_mm=300, b_mm=150, l_mm=200, frame_profile="E20"))
            self.assertEqual(price_text(pr), "EUR 39,37")

            measured = store.save_item("A-30", self.valid_bu())
            self.assertEqual(price_text(measured), "EUR 43,03/m²")

            automatic = store.save_item("A-40", dict(defaults("BU"), a_mm=1640, b_mm=1020, length_mm=1500, thickness_mode="AIRKAN_BC"))
            self.assertEqual(automatic["parameters"]["t_mm"], 1.2)
            self.assertEqual(automatic["parameters"]["airkan_a_mm"], 0)
            self.assertEqual(price_text(automatic), "EUR 56,24/m²")

    def test_area_override_drives_on_demand_total_and_can_be_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", dict(defaults("BU"), a_mm=1640, b_mm=1020, length_mm=1500, t_mm=1.2))
            self.assertEqual(area_text(item), "")
            self.assertEqual(rate_text(item), "EUR 56,24/m²")
            self.assertEqual(total_price_text(item), "")
            store.set_area_override("A-10", "8,5".replace(",", "."))
            self.assertEqual(area_text(item), "8,500 *")
            self.assertEqual(total_price_text(item), "EUR 478,04")
            self.assertNotIn("unit_price_eur", item)
            store.set_area_override("A-10", None)
            self.assertEqual(area_text(item), "")

    def test_confirmed_quote_prices_on_request_special_tee_and_expires_on_change(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            parameters = dict(defaults("TEE_SPECIAL"), variant="TASYMM", a_mm=300, b_mm=200, c_mm=400, d_mm=200, length_mm=1000, branch_length_mm=300)
            item = store.save_item("A-10", parameters)
            self.assertEqual(price_text(item), "On request")
            quoted = store.set_confirmed_quote("A-10", "321.45", "Airkan Q-2026-103")
            self.assertEqual(quoted["confirmed_quote"]["reference"], "Airkan Q-2026-103")
            self.assertEqual(price_text(quoted), "EUR 321,45")
            changed = store.save_item("A-10", dict(parameters, d_mm=250))
            self.assertNotIn("confirmed_quote", changed)
            self.assertEqual(price_text(changed), "On request")

    def test_legacy_unpriced_thickness_remains_loadable(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            item["parameters"]["t_mm"] = 2.0
            store.save()

            reopened = ProjectStore(folder)
            self.assertEqual(reopened.item("A-10")["parameters"]["t_mm"], 2.0)
            self.assertIn("no catalogue price", reopened.error_text("A-10"))
            self.assertEqual(price_text(reopened.item("A-10")), "")

    @staticmethod
    def item_endpoint(item_id, port):
        return {"kind": "item", "id": item_id, "port": port}

    @staticmethod
    def external_endpoint(name):
        return {"kind": "external", "id": name, "port": ""}

    def test_missing_connections_are_nonoverrideable_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            issues = store.connection_issues("A-10")
            self.assertEqual([issue["code"] for issue in issues], ["NO PRECEDING PIECE", "NO NEXT PIECE"])
            self.assertFalse(any(issue["overrideable"] for issue in issues))

    def test_external_endpoints_satisfy_predecessor_and_successor(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            store.add_connection(self.external_endpoint("AHU"), self.item_endpoint("A-10", "JO_IN"))
            store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.external_endpoint("DAKDOORVOER"))
            self.assertEqual(store.connection_issues("A-10"), [])
            self.assertEqual(store.connection_summary("A-10", "in"), "EXT:AHU")
            self.assertEqual(store.connection_summary("A-10", "out"), "EXT:DAKDOORVOER")

    def test_same_neighbor_is_allowed_only_through_distinct_ports(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            tee = dict(defaults("TEE_RECT"), t_mm=0.95)
            store.save_item("A-20", tee)
            store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.item_endpoint("A-20", "JO_IN"))
            store.add_connection(self.item_endpoint("A-20", "JO_BRANCH"), self.item_endpoint("A-10", "JO_IN"))
            self.assertEqual(len(store.connections_for("A-10")), 2)
            with self.assertRaises(ValueError):
                store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.external_endpoint("AHU"))

    def test_fit_override_expires_after_geometry_change(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            smaller = dict(self.valid_bu(), a_mm=900)
            store.save_item("A-20", smaller)
            store.add_connection(self.external_endpoint("AHU"), self.item_endpoint("A-10", "JO_IN"))
            connection = store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.item_endpoint("A-20", "JO_IN"))
            store.add_connection(self.item_endpoint("A-20", "JO_OUT"), self.external_endpoint("UITLAAT"))
            self.assertIn("NEXT PIECE DOES NOT FIT", store.error_text("A-10"))
            self.assertIn("PRECEDING PIECE DOES NOT FIT", store.error_text("A-20"))
            store.accept_fit_override(connection["id"])
            self.assertEqual(store.error_text("A-10"), "")
            self.assertEqual(store.error_text("A-20"), "")
            store.item("A-10")["built_fingerprint"] = __import__("allshield_project").build_fingerprint(store.item("A-10"))
            store.item("A-20")["built_fingerprint"] = __import__("allshield_project").build_fingerprint(store.item("A-20"))
            store.save()
            store.save_item("A-20", dict(smaller, a_mm=850))
            self.assertIn("NEXT PIECE DOES NOT FIT", store.error_text("A-10"))
            self.assertEqual({item["id"] for item in store.dirty_items()}, {"A-10", "A-20"})

    def test_removing_item_removes_edges_and_reports_open_peer_port(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            store.save_item("A-20", self.valid_bu())
            store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.item_endpoint("A-20", "JO_IN"))
            store.remove_item("A-20")
            self.assertEqual(store.connections_for("A-10"), [])
            self.assertIn("NO NEXT PIECE", store.error_text("A-10"))

    def test_v1_scalar_references_migrate_to_port_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parameters = self.valid_bu()
            data = {
                "schema": "allshield-airkan-project-v1",
                "version": 1,
                "prefix": "GROEP-01",
                "items": [
                    {"id": "A-10", "from": "AHU", "to": "A-20", "parameters": parameters, "status": "Gewijzigd", "error": "", "built_fingerprint": ""},
                    {"id": "A-20", "from": "A-10", "to": "UITLAAT", "parameters": parameters, "status": "Gewijzigd", "error": "", "built_fingerprint": ""},
                ],
            }
            (root / "project.json").write_text(json.dumps(data), encoding="utf-8")
            store = ProjectStore(root)
            self.assertEqual(store.data["version"], 2)
            self.assertEqual(len(store.data["connections"]), 3)
            self.assertEqual(store.error_text("A-10"), "")
            self.assertEqual(store.error_text("A-20"), "")
            self.assertNotIn("from", store.item("A-10"))

    def test_stale_worker_result_is_rejected_after_connection_change(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            old_fingerprint = __import__("allshield_project").build_fingerprint(item)
            store.add_connection(self.external_endpoint("AHU"), self.item_endpoint("A-10", "JO_IN"))
            stage = store.staging_dir / "stale"
            stage.mkdir()
            staged_step = stage / "stale.step"
            staged_json = stage / "stale.json"
            staged_step.write_bytes(b"step")
            staged_json.write_text(json.dumps({
                "schema": "airkan-component-v3",
                "project_item": {"id": "A-10", "build_fingerprint": old_fingerprint},
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.commit_build("A-10", staged_step, staged_json)

    def test_port_specs_match_three_way_piece(self):
        names = [port["name"] for port in port_specs(dict(defaults("TEE_RECT"), t_mm=0.95))]
        self.assertEqual(names, ["JO_IN", "JO_OUT", "JO_BRANCH"])

    def test_grille_ports_and_size_use_catalogue_orientation(self):
        parameters = dict(defaults("GRILLE_FIRE"), variant="GE60XL", h_mm=200, b_mm=900)
        ports = port_specs(parameters)
        self.assertEqual([port["name"] for port in ports], ["JO_WALL_A", "JO_WALL_B"])
        self.assertEqual((ports[0]["width_mm"], ports[0]["height_mm"]), (900.0, 200.0))
        self.assertTrue(all(port["external_only"] for port in ports))
        self.assertEqual(size_text(parameters), "GE60XL H200 x B900 mm")

    def test_grille_rejects_mechanical_item_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            store.save_item("A-20", defaults("GRILLE_FIRE"))
            with self.assertRaisesRegex(ValueError, "only to an external"):
                store.add_connection(self.item_endpoint("A-10", "JO_OUT"), self.item_endpoint("A-20", "JO_WALL_A"))

    def test_buy_outside_grille_has_external_and_duct_ports(self):
        parameters = dict(defaults("BUY"), supplier="Renson", article_code="411/900", description="Buitenrooster",
                          source_step="C:/models/buitenrooster.step", a_mm=900, b_mm=700, airflow_role="AANZUIG",
                          price_status="ON_REQUEST", unit_price_eur=0, price_source="Leverancierspagina")
        ports = port_specs(parameters)
        self.assertEqual([port["name"] for port in ports], ["JO_OUTSIDE", "JO_DUCT"])
        self.assertTrue(ports[0]["external_only"])
        self.assertFalse(ports[1]["external_only"])
        self.assertEqual((ports[1]["width_mm"], ports[1]["height_mm"]), (900.0, 700.0))
        self.assertEqual(size_text(parameters), "Renson 411/900 | 900 x 700 mm")

    def test_cm_fingerprint_uses_step_content_not_path(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "first.step"
            second = Path(folder) / "second.step"
            first.write_bytes(b"same STEP content")
            second.write_bytes(first.read_bytes())
            base = dict(defaults("CM"), description="Plenum")
            item = {"id": "A-10", "connection_fingerprint": "", "parameters": dict(base, source_step=str(first))}
            first_fingerprint = build_fingerprint(item)
            item["parameters"]["source_step"] = str(second)
            self.assertEqual(build_fingerprint(item), first_fingerprint)
            second.write_bytes(b"changed STEP content")
            self.assertNotEqual(build_fingerprint(item), first_fingerprint)

    def test_prefix_change_marks_items_dirty(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            item["built_fingerprint"] = __import__("allshield_project").build_fingerprint(item)
            store.save()
            self.assertFalse(store.dirty_items())
            self.assertTrue(store.set_prefix("AHU-02"))
            self.assertEqual(store.item("A-10")["parameters"]["prefix"], "AHU-02")
            self.assertEqual(store.dirty_items()[0]["id"], "A-10")

    def test_commit_replaces_only_registered_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            old_step = store.step_dir / "old.step"
            old_json = store.root / "old.json"
            old_fcstd = store.root / "old.FCStd"
            old_step.write_bytes(b"old")
            old_json.write_text("{}", encoding="utf-8")
            old_fcstd.write_bytes(b"legacy")
            item.update(step_file="step/old.step", json_file="old.json", legacy_fcstd_file="old.FCStd")
            store.save()
            stage = store.staging_dir / "job"
            stage.mkdir()
            staged_step = stage / "GROEP-01_A-10_BU.step"
            staged_step.write_bytes(b"new-step")
            staged_json = stage / "GROEP-01_A-10_BU.json"
            staged_json.write_text(json.dumps({
                "schema": "airkan-component-v3",
                "parameters": item["parameters"],
                "project_item": {"id": "A-10"},
                "order": {"one_sided_price_area_m2": 3.6, "requested_nonstandard_frame_count": 2, "unit_price_eur": 203.17, "pricing_status": "CATALOGUE_CALCULATION"},
            }), encoding="utf-8")
            store.commit_build("A-10", staged_step, staged_json)
            self.assertFalse(old_step.exists())
            self.assertFalse(old_json.exists())
            self.assertFalse(old_fcstd.exists())
            self.assertEqual((store.root / store.item("A-10")["step_file"]).read_bytes(), b"new-step")
            accepted = json.loads((store.json_dir / "A-10.json").read_text(encoding="utf-8"))
            self.assertEqual(accepted["project_item"]["id"], "A-10")
            self.assertEqual(store.item("A-10")["measured_area_m2"], 3.6)
            self.assertNotIn("accepted_unit_price_eur", store.item("A-10"))
            self.assertEqual(area_text(store.item("A-10")), "3,600")
            self.assertEqual(rate_text(store.item("A-10")), "EUR 43,03/m²")
            self.assertEqual(total_price_text(store.item("A-10")), "EUR 162,65")
            self.assertNotIn("unit_price_eur", accepted["order"])
            self.assertEqual(store.dirty_items(), [])
            changed = dict(store.item("A-10")["parameters"], length_mm=1100)
            store.save_item("A-10", changed)
            self.assertEqual(price_text(store.item("A-10")), "EUR 56,70/m²")

    def test_empty_staged_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            store.save_item("A-10", self.valid_bu())
            staged_step = store.staging_dir / "empty.step"
            staged_json = store.staging_dir / "empty.json"
            staged_step.touch()
            staged_json.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.commit_build("A-10", staged_step, staged_json)

    def test_old_step_survives_project_save_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            old_step = store.step_dir / "old.step"
            old_step.write_bytes(b"old")
            item["step_file"] = "step/old.step"
            store.save()
            staged_step = store.staging_dir / "new.step"
            staged_step.write_bytes(b"new")
            staged_json = store.staging_dir / "new.json"
            staged_json.write_text(json.dumps({
                "schema": "airkan-component-v3",
                "project_item": {"id": "A-10"},
            }), encoding="utf-8")
            with patch.object(store, "save", side_effect=OSError("disk full")), self.assertRaises(OSError):
                store.commit_build("A-10", staged_step, staged_json)
            self.assertTrue(old_step.is_file())

    def test_remove_item_deletes_only_registered_files(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            step = store.step_dir / "registered.step"
            parameters = store.json_dir / "A-10.json"
            unrelated = store.step_dir / "keep.step"
            step.write_bytes(b"step")
            parameters.write_text("{}", encoding="utf-8")
            unrelated.write_bytes(b"keep")
            item.update(step_file="step/registered.step", json_file="json/A-10.json")
            store.save()
            store.remove_item("A-10")
            self.assertFalse(step.exists())
            self.assertFalse(parameters.exists())
            self.assertTrue(unrelated.exists())

    def test_absolute_registered_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(folder)
            item = store.save_item("A-10", self.valid_bu())
            item["step_file"] = str(Path(folder).resolve() / "outside.step")
            with self.assertRaises(ValueError):
                store.old_artifacts(["A-10"])

    def test_size_and_output_name(self):
        parameters = self.valid_bu()
        item = {"id": "A-10", "parameters": parameters}
        resolved = __import__("airkan_builder.rules", fromlist=["resolve"]).resolve(parameters)
        self.assertEqual(size_text(parameters), "1000 x 800 x 1000 mm")
        self.assertTrue(output_basename(item, resolved).startswith("GROEP-01_A-10_BU_"))

    def test_invalid_id(self):
        with self.assertRaises(ValueError):
            validate_item_id("A 10")

    def test_legacy_prefix_to_numbered_id(self):
        self.assertEqual(item_id_from_legacy_prefix("A_20"), "A-20")
        self.assertEqual(item_id_from_legacy_prefix("B70"), "B-70")
        self.assertIsNone(item_id_from_legacy_prefix("GROEP-01"))

    def test_v301_export_recovers_id_from_filename_and_stays_dirty(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parameters = self.valid_bu()
            parameters.pop("prefix")
            (root / "B70_BU_example.json").write_text(json.dumps({
                "schema": "airkan-component-v3",
                "parameters": parameters,
            }), encoding="utf-8")
            (root / "B70_BU_example.step").write_bytes(b"legacy-step")
            (root / "B70_BU_example.FCStd").write_bytes(b"legacy-freecad")
            store = ProjectStore(root)
            item = store.item("B-70")
            self.assertEqual(item["status"], "Gewijzigd")
            self.assertEqual(item["legacy_fcstd_file"], "B70_BU_example.FCStd")
            self.assertEqual([row["id"] for row in store.dirty_items()], ["B-70"])


if __name__ == "__main__":
    unittest.main()