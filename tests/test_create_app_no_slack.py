# -*- coding: utf-8 -*-

import os
import unittest

from cineapp import create_app


class CreateAppNoSlackTestCase(unittest.TestCase):
    """Tests for create_app() when SLACK_NOTIFICATION_ENABLE is missing"""

    CONFIG_PATH = 'tests/ressources/settings_tests_no_slack_enable.cfg'

    # --- Line 152: SLACK_NOTIFICATION_ENABLE missing → RuntimeError ---
    def test_create_app_slack_enable_missing(self):
        """create_app raises RuntimeError when SLACK_NOTIFICATION_ENABLE is missing"""
        with self.assertRaises(RuntimeError) as ctx:
            create_app(self.CONFIG_PATH)
        assert "SLACK_NOTIFICATION_ENABLE" in str(ctx.exception)
