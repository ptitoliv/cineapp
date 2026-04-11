# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

from cineapp import create_app


class CreateAppEnvKeysTestCase(unittest.TestCase):
    """Tests for create_app() importing API keys from environment variables"""

    CONFIG_PATH = 'tests/ressources/settings_tests_init.cfg'

    # --- Lines 158-159: API keys imported from environment variables ---
    def test_create_app_api_keys_from_env(self):
        """create_app imports API keys from environment when missing from config"""
        env_vars = {
            "API_KEY": "env-api-key",
            "SLACK_TOKEN": "env-slack-token",
            "DEEPL_API_KEY": "env-deepl-key",
            "IGDB_CLIENT_ID": "env-igdb-id",
            "IGDB_CLIENT_SECRET": "env-igdb-secret"
        }
        with patch.dict(os.environ, env_vars):
            app = create_app(self.CONFIG_PATH)
            for key, value in env_vars.items():
                assert app.config[key] == value
