from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_skill_layout import validate_skill


class ValidateSkillLayoutTests(unittest.TestCase):
    def test_helper_path_ignores_sentence_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "decomp"
            skills_root = root / "skills"
            skill_dir = skills_root / "matching-decomp"
            scripts_dir = root / "scripts"

            skill_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "parse_compare.py").write_text("", encoding="utf-8")

            skill = skill_dir / "SKILL.md"
            skill.write_text(
                "---\n"
                "name: matching-decomp\n"
                "description: Test skill.\n"
                "---\n\n"
                "Run ../../scripts/parse_compare.py.\n",
                encoding="utf-8",
            )

            self.assertEqual(validate_skill(skill, skills_root), [])


if __name__ == "__main__":
    unittest.main()
