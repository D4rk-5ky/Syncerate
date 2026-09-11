import tempfile
import unittest
from pathlib import Path

from syncerate.datasets import (
    load_dataset_pairs,
    parse_destination_line,
    read_dataset_list,
)
from syncerate.errors import EXIT_LIST_ERROR, SyncerateError
from tests.helpers import make_config, make_logger


class DatasetTests(unittest.TestCase):
    def test_read_dataset_list_ignores_blank_and_comment_lines(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "list"
            path.write_text("# comment\n\npool/a\n  pool/b  \n", encoding="utf-8")
            self.assertEqual(read_dataset_list(str(path)), ["pool/a", "pool/b"])

    def test_destination_extra_args_preserve_quoted_colon_space(self):
        dataset, args = parse_destination_line(
            'backup/data: --identifier "label: nightly" --no-sync-snap'
        )
        self.assertEqual(dataset, "backup/data")
        self.assertEqual(args, ["--identifier", "label: nightly", "--no-sync-snap"])

    def test_destination_extra_args_report_unclosed_quote(self):
        with self.assertRaisesRegex(ValueError, "Could not parse extra arguments"):
            parse_destination_line('backup/data: --identifier "broken')

    def test_empty_active_lists_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            dest = Path(td) / "dest"
            source.write_text("# only comment\n", encoding="utf-8")
            dest.write_text("\n", encoding="utf-8")
            cfg = make_config(
                source_list_path=str(source),
                destination_list_path=str(dest),
            )
            with self.assertRaises(SyncerateError) as cm:
                load_dataset_pairs(cfg, make_logger("empty-lists"))
            self.assertEqual(cm.exception.exit_code, EXIT_LIST_ERROR)

    def test_mismatched_lengths_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            dest = Path(td) / "dest"
            source.write_text("pool/a\npool/b\n", encoding="utf-8")
            dest.write_text("backup/a\n", encoding="utf-8")
            cfg = make_config(source_list_path=str(source), destination_list_path=str(dest))
            with self.assertRaises(SyncerateError) as cm:
                load_dataset_pairs(cfg, make_logger("length-mismatch"))
            self.assertEqual(cm.exception.exit_code, EXIT_LIST_ERROR)

    def test_mismatched_leaf_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            dest = Path(td) / "dest"
            source.write_text("pool/a\n", encoding="utf-8")
            dest.write_text("backup/b\n", encoding="utf-8")
            cfg = make_config(source_list_path=str(source), destination_list_path=str(dest))
            with self.assertRaises(SyncerateError):
                load_dataset_pairs(cfg, make_logger("name-mismatch"))

    def test_trailing_slash_does_not_accidentally_match_empty_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            dest = Path(td) / "dest"
            source.write_text("pool/a/\n", encoding="utf-8")
            dest.write_text("backup/a/\n", encoding="utf-8")
            cfg = make_config(source_list_path=str(source), destination_list_path=str(dest))
            with self.assertRaises(SyncerateError):
                load_dataset_pairs(cfg, make_logger("trailing-slash"))

    def test_matching_pairs_preserve_per_destination_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            dest = Path(td) / "dest"
            source.write_text("pool/a\n", encoding="utf-8")
            dest.write_text('backup/a: --identifier "nightly backup"\n', encoding="utf-8")
            cfg = make_config(source_list_path=str(source), destination_list_path=str(dest))
            pairs = load_dataset_pairs(cfg, make_logger("matching-pairs"))
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0].source, "pool/a")
            self.assertEqual(pairs[0].destination, "backup/a")
            self.assertEqual(pairs[0].extra_arguments, ("--identifier", "nightly backup"))


if __name__ == "__main__":
    unittest.main()
