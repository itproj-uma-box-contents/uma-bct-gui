import os
import tempfile
import unittest
from pathlib import Path

import main


class ImageReferenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path.cwd() / "Example batch"

    def test_plain_paths_and_literal_formulas(self):
        cases = [
            ("Box Images/café #1.png", "Box Images/café #1.png"),
            (r"Box Images\box.png", "Box Images/box.png"),
            ('=HYPERLINK("Box Images/box.png","Box 1")', "Box Images/box.png"),
            (' = hyperlink ( "Box Images/box.png" ; "Box 1" ) ', "Box Images/box.png"),
            ('=HYPERLINK("Box Images/100%20.png")', "Box Images/100%20.png"),
            ('=HYPERLINK("Box Images/a""b.png","Quoted")', 'Box Images/a"b.png'),
            ("Box Images/100%20.png", "Box Images/100%20.png"),
        ]
        for reference, expected in cases:
            with self.subTest(reference=reference):
                self.assertEqual(main.resolve_image_path(self.folder, reference), self.folder / expected)

    def test_native_hyperlinks_and_file_urls_are_decoded_once(self):
        expected = self.folder / "Box Images/café #100%20.png"
        self.assertEqual(main.resolve_image_path(self.folder, expected.as_uri()), expected)
        self.assertEqual(
            main.resolve_image_path(self.folder, "Box%20Images/caf%C3%A9%20%23100%2520.png", url_encoded=True),
            expected,
        )
        self.assertEqual(main.resolve_image_path(self.folder, str(expected)), expected)

    def test_blank_references_are_intentional(self):
        self.assertIsNone(main.resolve_image_path(self.folder, ""))
        self.assertIsNone(main.resolve_image_path(self.folder, '=HYPERLINK("","")'))

    def test_native_link_falls_back_to_an_existing_literal_percent_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            literal = folder / "100%20.png"
            literal.touch()
            self.assertEqual(main.resolve_image_path(folder, literal.name, url_encoded=True), literal)
            decoded = folder / "100 .png"
            decoded.touch()
            self.assertEqual(main.resolve_image_path(folder, literal.name, url_encoded=True), decoded)
            self.assertEqual(main.resolve_image_path(folder, literal.as_uri(), url_encoded=True), literal)

    def test_computed_formulas_remote_urls_and_invalid_paths_are_rejected(self):
        for value in ('=HYPERLINK(A1,"Box")', '=HYPERLINK("a" & "b","Box")', '=SUM(1,2)',
                      'https://example.com/box.png', 'bad\x00path', '=HYPERLINK("unclosed") trailing'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    main.resolve_image_path(self.folder, value)

    @unittest.skipUnless(os.name == "nt", "Windows drive and share syntax")
    def test_windows_drive_and_share_paths(self):
        self.assertEqual(main.resolve_image_path(self.folder, r"C:\Images\box.png"), Path("C:/Images/box.png"))
        self.assertEqual(main.resolve_image_path(self.folder, "file:///C:/Images/box%201.png"), Path("C:/Images/box 1.png"))
        self.assertEqual(main.resolve_image_path(self.folder, "file://server/share/box.png"), Path("//server/share/box.png"))


if __name__ == "__main__":
    unittest.main()
