import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import main

try:
    import openpyxl
    from openpyxl.comments import Comment
    from openpyxl.styles import PatternFill
except ImportError:
    openpyxl = None


class CatalogueTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.fields = ["Description", main.IMAGE_LINK_FIELD, main.REVIEWED_FIELD]

    def write_csv(self):
        path = self.folder / "catalogue.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(self.fields)
            writer.writerow(["Box, with a comma", "crops/box.png", "False"])
        return path

    def assert_no_temp_files(self, path):
        self.assertEqual(list(self.folder.iterdir()), [path])


class CatalogueTests(CatalogueTestCase):
    def test_csv_round_trip_preserves_columns_and_text(self):
        path = self.write_csv()
        fields, rows = main.load_rows(path)
        rows[0]["Description"] = "First line\nSecond line — café"
        fields.append(main.FLAGS_FIELD)
        rows[0][main.FLAGS_FIELD] = "Missing Box"

        main.save_rows(path, fields, rows)

        saved_fields, saved_rows = main.load_rows(path)
        self.assertEqual(saved_fields, fields)
        self.assertEqual(saved_rows, rows)
        self.assert_no_temp_files(path)

    def test_csv_accepts_utf8_bom(self):
        path = self.write_csv()
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

        fields, rows = main.load_rows(path)

        self.assertEqual(fields, self.fields)
        self.assertEqual(rows[0]["Description"], "Box, with a comma")

    def test_csv_rejects_invalid_headers(self):
        path = self.folder / "catalogue.csv"
        for content in ("", "Description,Description\nA,B\n", "Description,\nA,B\n"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(main.CatalogueError):
                    main.load_rows(path)

    def test_csv_write_failure_keeps_original_and_removes_temp_file(self):
        path = self.write_csv()
        original = path.read_bytes()
        fields, rows = main.load_rows(path)
        rows[0]["Description"] = "Changed"

        with patch.object(csv.DictWriter, "writerows", side_effect=OSError("Disk full")):
            with self.assertRaises(main.CatalogueError):
                main.save_rows(path, fields, rows)

        self.assertEqual(path.read_bytes(), original)
        self.assert_no_temp_files(path)

    def test_csv_replace_failure_keeps_original_and_removes_temp_file(self):
        path = self.write_csv()
        original = path.read_bytes()
        fields, rows = main.load_rows(path)

        with patch("main.os.replace", side_effect=OSError("Permission denied")):
            with self.assertRaises(main.CatalogueError):
                main.save_rows(path, fields, rows)

        self.assertEqual(path.read_bytes(), original)
        self.assert_no_temp_files(path)

    def test_csv_refuses_to_overwrite_external_changes(self):
        path = self.write_csv()
        fields, rows = main.load_rows(path)
        revision = main.catalogue_revision(path)
        external_content = path.read_bytes().replace(b"Box, with a comma", b"External edit")
        path.write_bytes(external_content)
        rows[0]["Description"] = "GUI edit"

        with self.assertRaises(main.CatalogueError):
            main.save_rows(path, fields, rows, expected_revision=revision)

        self.assertEqual(path.read_bytes(), external_content)
        self.assert_no_temp_files(path)

    def test_csv_detects_external_changes_during_save(self):
        path = self.write_csv()
        fields, rows = main.load_rows(path)
        revision = main.catalogue_revision(path)
        external_content = path.read_bytes().replace(b"Box, with a comma", b"External edit")
        original_writerows = csv.DictWriter.writerows

        def write_then_change_original(writer, values):
            original_writerows(writer, values)
            path.write_bytes(external_content)

        with patch.object(csv.DictWriter, "writerows", new=write_then_change_original):
            with self.assertRaises(main.CatalogueError):
                main.save_rows(path, fields, rows, expected_revision=revision)

        self.assertEqual(path.read_bytes(), external_content)
        self.assert_no_temp_files(path)


@unittest.skipIf(openpyxl is None, "Install the excel extra to test XLSX catalogues")
class ExcelCatalogueTests(CatalogueTestCase):
    def write_workbook(self):
        path = self.folder / "catalogue.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        self.fields += ["Count", "Date", "Selected", "Formula", "Website"]
        sheet.append(self.fields)
        sheet.append([
            "Original description", "box.png", False, 12, datetime(2024, 5, 6),
            True, "=D2*2", "Archive website",
        ])
        sheet["B2"].hyperlink = "crops/box.png"
        sheet["A2"].comment = Comment("Keep this note", "Reviewer")
        sheet["A2"].fill = PatternFill(fill_type="solid", fgColor="FFFFCC00")
        sheet["D2"].number_format = "0.00"
        sheet["E2"].number_format = "yyyy-mm-dd"
        sheet["H2"].hyperlink = "https://example.com/archive"
        workbook.create_sheet("Notes")["A1"] = "Other sheet stays intact"
        workbook.save(path)
        workbook.close()
        return path

    def read_workbook(self, path):
        workbook = openpyxl.load_workbook(path)
        self.addCleanup(workbook.close)
        return workbook

    def test_xlsx_rejects_populated_columns_without_headers(self):
        path = self.folder / "catalogue.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.append(["Description", main.REVIEWED_FIELD])
        workbook.active.append(["Record", False])
        workbook.active["C3"] = "A note without a column header"
        workbook.save(path)
        workbook.close()
        original = path.read_bytes()

        with self.assertRaises(main.CatalogueError):
            main.load_rows(path)

        self.assertEqual(path.read_bytes(), original)

    def test_xlsx_accepts_empty_formatted_columns_without_headers(self):
        path = self.folder / "catalogue.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.append(["Description", main.REVIEWED_FIELD])
        workbook.active.append(["Record", False])
        workbook.active["C3"].fill = PatternFill(fill_type="solid", fgColor="FFFFCC00")
        workbook.save(path)
        workbook.close()

        fields, rows = main.load_rows(path)

        self.assertEqual(fields, ["Description", main.REVIEWED_FIELD])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Description"], "Record")

    def test_xlsx_save_does_not_replace_populated_unnamed_columns_with_flags(self):
        path = self.folder / "catalogue.xlsx"
        fields = ["Description", main.REVIEWED_FIELD, main.FLAGS_FIELD]
        rows = [{"Description": "Changed", main.REVIEWED_FIELD: "False", main.FLAGS_FIELD: "Missing Box"}]
        for position in ("C2", "C3"):
            with self.subTest(position=position):
                workbook = openpyxl.Workbook()
                workbook.active.append(["Description", main.REVIEWED_FIELD])
                workbook.active.append(["Record", False])
                workbook.active[position] = "Keep this note"
                workbook.save(path)
                workbook.close()
                original = path.read_bytes()

                with self.assertRaises(main.CatalogueError):
                    main.save_rows(path, fields, rows)

                self.assertEqual(path.read_bytes(), original)
                self.assert_no_temp_files(path)

    def test_xlsx_round_trip_preserves_metadata_and_original_types(self):
        path = self.write_workbook()
        fields, rows = main.load_rows(path)
        rows[0]["Description"] = "Corrected description"
        fields.append(main.FLAGS_FIELD)
        rows[0][main.FLAGS_FIELD] = "Missing Box"

        main.save_rows(path, fields, rows)

        workbook = self.read_workbook(path)
        sheet = workbook.active
        self.assertEqual(sheet["A2"].value, "Corrected description")
        self.assertEqual(sheet["A2"].comment.text, "Keep this note")
        self.assertEqual(sheet["A2"].fill.fgColor.rgb, "FFFFCC00")
        self.assertEqual(sheet["B2"].hyperlink.target, "crops/box.png")
        self.assertIs(sheet["C2"].value, False)
        self.assertEqual(sheet["D2"].value, 12)
        self.assertEqual(sheet["D2"].number_format, "0.00")
        self.assertEqual(sheet["E2"].value, datetime(2024, 5, 6))
        self.assertEqual(sheet["E2"].number_format, "yyyy-mm-dd")
        self.assertIs(sheet["F2"].value, True)
        self.assertEqual(sheet["G2"].value, "=D2*2")
        self.assertEqual(sheet["G2"].data_type, "f")
        self.assertEqual(sheet["H2"].hyperlink.target, "https://example.com/archive")
        self.assertEqual(sheet["I1"].value, main.FLAGS_FIELD)
        self.assertEqual(sheet["I2"].value, "Missing Box")
        self.assertEqual(workbook["Notes"]["A1"].value, "Other sheet stays intact")
        self.assert_no_temp_files(path)

    def test_xlsx_preserves_and_saves_literal_equals_text(self):
        path = self.write_workbook()
        workbook = self.read_workbook(path)
        workbook.active["A2"] = "=1+2"
        workbook.active["A2"].data_type = "s"
        workbook.save(path)
        fields, rows = main.load_rows(path)

        main.save_rows(path, fields, rows)
        saved = self.read_workbook(path)
        self.assertEqual(saved.active["A2"].value, "=1+2")
        self.assertEqual(saved.active["A2"].data_type, "s")

        rows[0]["Description"] = "=3+4"
        main.save_rows(path, fields, rows)
        edited = self.read_workbook(path)
        self.assertEqual(edited.active["A2"].value, "=3+4")
        self.assertEqual(edited.active["A2"].data_type, "s")

    def test_xlsx_normalizes_numeric_and_boolean_reviewed_values(self):
        path = self.folder / "catalogue.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.append(self.fields)
        for value in (True, False, 1, 0):
            workbook.active.append(["Record", "crop.png", value])
        workbook.save(path)
        workbook.close()

        fields, rows = main.load_rows(path)

        self.assertEqual([row[main.REVIEWED_FIELD] for row in rows], ["True", "False", "True", "False"])
        rows[1][main.REVIEWED_FIELD] = "True"
        main.save_rows(path, fields, rows)
        saved = self.read_workbook(path)
        self.assertIs(saved.active["C3"].value, True)
        self.assertEqual(saved.active["C4"].value, 1)
        self.assertEqual(saved.active["C5"].value, 0)

    def test_xlsx_deletes_correct_record_with_blank_row_gaps(self):
        path = self.write_workbook()
        workbook = self.read_workbook(path)
        sheet = workbook.active
        sheet.append([None] * len(self.fields))
        sheet.append(["Keep this record", "second.png", False])
        sheet["A4"].comment = Comment("Keep second note", "Reviewer")
        workbook.save(path)
        fields, rows = main.load_rows(path)
        self.assertEqual(len(rows), 2)

        main.save_rows(path, fields, rows[1:])

        saved = self.read_workbook(path)
        self.assertIsNone(saved.active["A2"].value)
        self.assertEqual(saved.active["A3"].value, "Keep this record")
        self.assertEqual(saved.active["A3"].comment.text, "Keep second note")
        self.assertEqual(len(main.load_rows(path)[1]), 1)

    def test_xlsx_repeated_deletes_keep_correct_row_positions(self):
        path = self.write_workbook()
        workbook = self.read_workbook(path)
        workbook.active.append(["Second record", "second.png", False])
        workbook.active.append(["Third record", "third.png", False])
        workbook.active["A4"].comment = Comment("Third record note", "Reviewer")
        workbook.save(path)
        fields, rows = main.load_rows(path)
        remaining = rows[1:]

        revision = main.save_rows(path, fields, remaining)
        main.save_rows(path, fields, remaining[1:], expected_revision=revision)

        saved = self.read_workbook(path)
        self.assertEqual(saved.active["A2"].value, "Third record")
        self.assertEqual(saved.active["A2"].comment.text, "Third record note")
        self.assertEqual(len(main.load_rows(path)[1]), 1)

    def test_xlsx_delete_moves_hyperlinks_without_creating_ghost_rows(self):
        path = self.write_workbook()
        workbook = self.read_workbook(path)
        sheet = workbook.active
        sheet.append(["Second record", "second.png", False, None, None, None, None, "Second website"])
        sheet["B3"].hyperlink = "crops/second.png"
        sheet["H3"].hyperlink = "https://example.com/second"
        workbook.save(path)
        fields, rows = main.load_rows(path)

        main.save_rows(path, fields, rows[1:])

        saved_fields, saved_rows = main.load_rows(path)
        self.assertEqual(saved_fields, fields)
        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_rows[0]["Description"], "Second record")
        self.assertEqual(saved_rows[0][main.IMAGE_LINK_FIELD], "crops/second.png")
        saved = self.read_workbook(path)
        sheet = saved.active
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet["B2"].hyperlink.target, "crops/second.png")
        self.assertEqual(sheet["B2"].hyperlink.ref, "B2")
        self.assertEqual(sheet["H2"].hyperlink.target, "https://example.com/second")
        self.assertEqual(sheet["H2"].hyperlink.ref, "H2")

    def test_xlsx_write_failure_keeps_original_and_removes_temp_file(self):
        path = self.write_workbook()
        original = path.read_bytes()
        fields, rows = main.load_rows(path)

        with patch.object(openpyxl.Workbook, "save", side_effect=OSError("Disk full")):
            with self.assertRaises(main.CatalogueError):
                main.save_rows(path, fields, rows)

        self.assertEqual(path.read_bytes(), original)
        self.assert_no_temp_files(path)

    def test_xlsx_refuses_to_overwrite_external_changes(self):
        path = self.write_workbook()
        fields, rows = main.load_rows(path)
        revision = main.catalogue_revision(path)
        workbook = self.read_workbook(path)
        workbook["Notes"]["A1"] = "An external correction"
        workbook.save(path)
        external_content = path.read_bytes()

        with self.assertRaises(main.CatalogueError):
            main.save_rows(path, fields, rows, expected_revision=revision)

        self.assertEqual(path.read_bytes(), external_content)
        self.assert_no_temp_files(path)

    def test_corrupt_xlsx_has_readable_error(self):
        path = self.folder / "catalogue.xlsx"
        path.write_text("This is not an Excel workbook", encoding="utf-8")

        with self.assertRaises(main.CatalogueError):
            main.load_rows(path)


if __name__ == "__main__":
    unittest.main()
