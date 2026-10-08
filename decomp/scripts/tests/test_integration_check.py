from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integration_check import validate_document


def evidence(regions=None):
    return {
        "target": "FS_LoadOverlay",
        "regions": regions or {
            "usa": {
                "function": {"entry": "0x02042540", "size": 0x30},
                "object": {"name": "overlay.o", "start": "0x0204253C", "end": "0x020425D3"},
                "range": {"kind": "delink", "start": "0x0204253C", "end": "0x020425D3"},
                "padding": {"before": [], "after": [{"start": "0x0204256A", "end": "0x0204256B"}]},
                "next_boundary": "0x020425D4",
                "evidence": ["xMAP boundary", "objdump object layout"],
                "independent_evidence": True,
            }
        },
    }


class IntegrationEvidenceTests(unittest.TestCase):
    def test_normalizes_function_object_and_range_separately(self):
        result = validate_document(evidence())
        region = result["regions"]["usa"]
        self.assertEqual(region["function"]["entry"], 0x02042540)
        self.assertEqual(region["object"]["start"], 0x0204253C)
        self.assertEqual(region["range"]["start"], 0x0204253C)
        self.assertEqual(region["padding"]["after"][0]["bytes"], 2)

    def test_requires_independent_evidence_for_multiple_regions(self):
        payload = evidence({
            "usa": evidence()["regions"]["usa"],
            "eur": {
                "function": {"entry": "0x02042584", "size": 0x30},
                "object": {"name": "overlay.o", "start": "0x02042580", "end": "0x02042617"},
                "range": {"kind": "delink", "start": "0x02042580", "end": "0x02042617"},
                "padding": {"before": [], "after": []},
                "evidence": ["mirrored from USA"],
                "independent_evidence": False,
            },
        })
        with self.assertRaises(ValueError):
            validate_document(payload)

    def test_rejects_function_outside_declared_range(self):
        payload = evidence({
            "usa": {
                "function": {"entry": "0x02043000", "size": 0x30},
                "object": {"name": "overlay.o", "start": "0x0204253C", "end": "0x020425D3"},
                "range": {"kind": "delink", "start": "0x0204253C", "end": "0x020425D3"},
                "padding": {"before": [], "after": []},
                "evidence": ["xMAP"],
            }
        })
        with self.assertRaises(ValueError):
            validate_document(payload)


if __name__ == "__main__":
    unittest.main()
