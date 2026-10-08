from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from package_opencode import package_skills


class OpenCodePackageTests(unittest.TestCase):
    def test_bundle_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "decomp"
            skills = source / "skills" / "demo-skill"
            scripts = source / "scripts"

            skills.mkdir(parents=True)
            scripts.mkdir(parents=True)
            (skills / "SKILL.md").write_text(
                "---\n"
                "name: demo-skill\n"
                "description: Demo.\n"
                "---\n\n"
                "Run ../../scripts/example.py.\n",
                encoding="utf-8",
            )
            (scripts / "example.py").write_text("print('ok')\n", encoding="utf-8")

            output = Path(tmp) / "bundle"
            manifest = package_skills(source, output, force=False)

            packaged = output / "demo-skill" / "SKILL.md"
            runtime = output / "_runtime" / "example.py"

            self.assertEqual(manifest["skills"], ["demo-skill"])
            self.assertTrue(packaged.is_file())
            self.assertTrue(runtime.is_file())
            self.assertIn("../_runtime/example.py", packaged.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
