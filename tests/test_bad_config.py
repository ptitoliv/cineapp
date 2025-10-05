# -*- coding: utf-8 -*-

from cineapp import create_app
import unittest

class FlaskrTestCase(unittest.TestCase):

    def test_00_init_app(self):

        """
            Test parsing configuration file with special parameters
        """
        # No configuration file
        with self.assertRaises(Exception) as context:
            self.app = create_app()

        self.assertTrue('Pas de fichier de configuration disponible à cet emplacement' in str(context.exception))

        # Slack configuration not defined
        with self.assertRaises(Exception) as context:
            self.app = create_app('configs/settings_test_bad.cfg')

        self.assertTrue('SLACK_NOTIFICATION_ENABLE not defined in configuration file' in str(context.exception))

        # Slack configuration not defined
        self.app = create_app('configs/settings_test_bad_02.cfg')
        assert self.app.config['SLACK_NOTIFICATION_CHANNEL']['movie'] == None
        assert self.app.config['SLACK_NOTIFICATION_CHANNEL']['tvshow'] == None

        # Incorrect directories configuration
        with self.assertRaises(Exception) as context:
            self.app = create_app('configs/settings_test_bad_03.cfg')
