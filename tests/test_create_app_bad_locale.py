# -*- coding: utf-8 -*-

import unittest

from cineapp import create_app


class CreateAppBadLocaleTestCase(unittest.TestCase):
    """Tests for create_app() when the configured LOCALE is unavailable"""

    CONFIG_PATH = 'tests/ressources/settings_tests_bad_locale.cfg'

    # --- Lines 267-268: locale.setlocale raises locale.Error, which is caught
    # so the app still builds (dates simply stay unlocalized) ---
    def test_create_app_bad_locale_is_handled(self):
        """create_app builds successfully even if the configured LOCALE is invalid"""
        app = create_app(self.CONFIG_PATH)
        assert app is not None
