# -*- coding: utf-8 -*-

import os
import unittest

from cineapp import create_app


class CreateAppBadLogdirTestCase(unittest.TestCase):
    """Tests for create_app() when LOGDIR cannot be created"""

    CONFIG_PATH = 'tests/ressources/settings_tests_bad_logdir.cfg'

    # --- Lines 190-192: LOGDIR creation fails → OSError ---
    def test_create_app_logdir_creation_fails(self):
        """create_app raises OSError when LOGDIR cannot be created"""
        with self.assertRaises(OSError) as ctx:
            create_app(self.CONFIG_PATH)
        assert "Impossible de créer" in str(ctx.exception)
