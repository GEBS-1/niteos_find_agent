import os
import unittest
from unittest.mock import patch

from app.cost_guard import (
    cheap_mode_enabled,
    llm_owner_enabled,
    llm_verify_enabled,
    llm_web_enabled,
)


class CostGuardTests(unittest.TestCase):
    def test_cheap_mode_is_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(cheap_mode_enabled())
            self.assertFalse(llm_web_enabled())
            self.assertFalse(llm_owner_enabled())
            self.assertFalse(llm_verify_enabled())

    def test_legacy_flags_cannot_bypass_cheap_mode(self):
        env = {
            "HUNT_CHEAP_MODE": "1",
            "HUNT_LLM_WEB": "1",
            "HUNT_LLM_OWNER": "1",
            "HUNT_LLM_VERIFY": "1",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(llm_web_enabled())
            self.assertFalse(llm_owner_enabled())
            self.assertFalse(llm_verify_enabled())

    def test_deep_mode_requires_explicit_opt_in(self):
        env = {"HUNT_CHEAP_MODE": "0", "HUNT_LLM_OWNER": "1"}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(llm_owner_enabled())
            self.assertFalse(llm_web_enabled())


if __name__ == "__main__":
    unittest.main()
