# -*- coding: utf-8 -*-

import os
import unittest

from cineapp import create_app


class SlackBadConfigTestCase(unittest.TestCase):
    """Tests for create_app() edge cases in cineapp/__init__.py"""

    CONFIG_PATH = 'tests/ressources/settings_tests_init.cfg'

    # --- Line 125: config file does not exist → RuntimeError ---
    def test_create_app_missing_config(self):
        """create_app raises RuntimeError when config file does not exist"""
        with self.assertRaises(RuntimeError) as ctx:
            create_app('configs/nonexistent.cfg')
        assert "Pas de fichier de configuration" in str(ctx.exception)

    # --- Line 121: config loaded via absolute path ---
    def test_create_app_absolute_config_path(self):
        """create_app loads config via absolute path"""
        abs_path = os.path.join(os.getcwd(), self.CONFIG_PATH)
        app = create_app(abs_path)
        assert app.config['SECRET_KEY'] == 'test-secret-key'

    # --- Lines 138, 144, 150: Slack channels not configured → set to None ---
    def test_create_app_slack_no_channels(self):
        """create_app sets Slack channels to None when not configured"""
        app = create_app(self.CONFIG_PATH)
        assert app.config['SLACK_NOTIFICATION_CHANNEL']['movie'] is None
        assert app.config['SLACK_NOTIFICATION_CHANNEL']['tvshow'] is None
        assert app.config['SLACK_NOTIFICATION_CHANNEL']['videogame'] is None
