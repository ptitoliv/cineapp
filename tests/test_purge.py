# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

from cineapp import create_app
from cineapp.models import db, PushNotification


class StartupPurgeTestCase(unittest.TestCase):
    """Startup data purge gated by the CINEAPP_PURGE env var (sessions + push subs).

    Each case boots the whole application through create_app() — the same entry
    point run.py and gunicorn use — so the purge runs via the real startup path
    rather than by calling the helper directly.
    """

    CONFIG_PATH = 'configs/settings_tests_local.cfg'

    @classmethod
    def setUpClass(cls):
        # Build the schema once on the shared test database.
        cls.app = create_app(cls.CONFIG_PATH)
        with cls.app.app_context():
            db.drop_all()
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()

    def _add_subscription(self, endpoint, session_id):
        with self.app.app_context():
            db.session.add(PushNotification(endpoint_id=endpoint, public_key="k", auth_token="a", session_id=session_id))
            db.session.commit()

    def test_00_startup_without_env_keeps_data(self):
        """Booting the app without CINEAPP_PURGE leaves subscriptions and sessions intact."""
        self._add_subscription("https://push.example/keep", "keep-session")

        # Full application startup, making sure the purge flag is absent.
        with patch.dict(os.environ):
            os.environ.pop("CINEAPP_PURGE", None)
            create_app(self.CONFIG_PATH)

        with self.app.app_context():
            assert PushNotification.query.count() == 1

    def test_01_startup_with_env_wipes_data(self):
        """Booting the app with CINEAPP_PURGE=1 wipes every push subscription and session."""
        # The subscription seeded by test_00 is still in the database here.
        # Seed a server-side session that the startup purge must remove too.
        cache = self.app.session_interface.cache
        cache.set("a-session-token", {"user": 1})

        # Full application startup with the purge flag set.
        with patch.dict(os.environ, {"CINEAPP_PURGE": "1"}):
            create_app(self.CONFIG_PATH)

        with self.app.app_context():
            assert PushNotification.query.count() == 0
        assert cache.get("a-session-token") is None
