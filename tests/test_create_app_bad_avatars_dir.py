# -*- coding: utf-8 -*-

import os
import unittest

from cineapp import create_app


class CreateAppBadAvatarsTestCase(unittest.TestCase):
    """Tests for create_app() when AVATARS_FOLDER cannot be created"""

    CONFIG_PATH = 'tests/ressources/settings_tests_bad_avatars.cfg'

    @classmethod
    def tearDownClass(cls):
        """Recreate the main app to restore all global extensions"""
        if os.getenv("CI") == "True":
            create_app('tests/ressources/settings_tests_ci.cfg')
        else:
            create_app('configs/settings_tests_local.cfg')

    # --- Lines 198-199: AVATARS_FOLDER creation fails → OSError ---
    def test_create_app_avatars_creation_fails(self):
        """create_app raises OSError when AVATARS_FOLDER cannot be created"""
        with self.assertRaises(OSError) as ctx:
            create_app(self.CONFIG_PATH)
        assert "Impossible de créer" in str(ctx.exception)
