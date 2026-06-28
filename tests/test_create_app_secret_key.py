# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

from cineapp import create_app


class CreateAppSecretKeyEnvTestCase(unittest.TestCase):
    """Tests for create_app() importing SECRET_KEY from an environment variable"""

    CONFIG_PATH = 'tests/ressources/settings_tests_init.cfg'

    # --- Lines 191-192: SECRET_KEY injected through the environment ---
    def test_create_app_secret_key_from_env(self):
        """create_app overrides SECRET_KEY with the environment value when set"""
        with patch.dict(os.environ, {"SECRET_KEY": "env-secret-key-value"}):
            app = create_app(self.CONFIG_PATH)
            assert app.config["SECRET_KEY"] == "env-secret-key-value"
