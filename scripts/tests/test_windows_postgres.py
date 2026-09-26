import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location('windows_postgres', Path(__file__).parents[1] / 'windows_postgres.py')
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)


class PostgresLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('ROOT', self.root), ('CONFIG', self.root / '.setup/postgres.json')]:
            patcher = patch.object(pg, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sqlite_and_missing_configuration_fail_closed(self):
        with self.assertRaises(ValueError):
            pg.environment()
        with patch.dict(os.environ, {'CMH_SMS_DATABASE_URL': 'sqlite:///old.db'}):
            with self.assertRaises(ValueError):
                pg.setup()
        self.assertFalse(pg.CONFIG.exists())

    def test_existing_sqlite_is_preserved_and_does_not_block_postgres(self):
        database = self.root / 'backend/data/cmh_sms.db'
        database.parent.mkdir(parents=True)
        database.write_bytes(b'existing records')
        with patch.object(pg.subprocess, 'run'), patch.object(pg, 'provision') as provision, patch.object(pg, 'connect'), patch('builtins.print') as output:
            pg.setup()
        self.assertEqual(database.read_bytes(), b'existing records')
        self.assertTrue(pg.load_config()['provisioned'])
        provision.assert_called_once()
        self.assertTrue(any('records are not imported' in str(call) for call in output.call_args_list))

    def test_remote_url_is_verified_persisted_and_used_for_restart(self):
        url = 'postgresql://app:p%40ss%25word@server:5433/hospital'
        with patch.dict(os.environ, {'CMH_SMS_DATABASE_URL': url}), patch.object(pg, 'connect') as connect, patch.object(pg, 'provision') as provision:
            pg.setup()
            connect.assert_called_once()
            provision.assert_not_called()
        env = pg.environment()
        self.assertEqual(env['CMH_SMS_DATABASE_MODE'], 'postgres')
        self.assertEqual(env['CMH_SMS_SQLITE_REPLICA'], 'false')
        self.assertEqual(env['CMH_SMS_DATABASE_URL'], url.replace('postgresql:', 'postgresql+psycopg:'))

    def test_connection_failure_does_not_replace_saved_config(self):
        original = {'url': 'postgresql://app:old@localhost/original'}
        pg.save_config(original)
        with patch.dict(os.environ, {'CMH_SMS_DATABASE_URL': 'postgresql://app:new@host/new'}), patch.object(pg, 'connect', side_effect=pg.psycopg.OperationalError):
            with self.assertRaises(pg.psycopg.OperationalError):
                pg.setup()
        self.assertEqual(pg.load_config(), original)

    def test_fresh_setup_and_repeat_preserve_credentials(self):
        with patch.object(pg.subprocess, 'run'), patch.object(pg, 'provision') as provision, patch.object(pg, 'connect'):
            pg.setup()
            first = pg.load_config()
            pg.setup()
            self.assertEqual(pg.load_config(), first)
            provision.assert_called_once()
            self.assertTrue(first['provisioned'])

    def test_interrupted_provisioning_reuses_generated_password(self):
        with patch.object(pg.subprocess, 'run'), patch.object(pg, 'provision', side_effect=pg.psycopg.OperationalError):
            with self.assertRaises(pg.psycopg.OperationalError):
                pg.setup()
        first = pg.load_config()
        with patch.object(pg.subprocess, 'run'), patch.object(pg, 'provision'), patch.object(pg, 'connect'):
            pg.setup()
        self.assertEqual(first['url'], pg.load_config()['url'])

    def test_existing_role_and_database_are_not_changed(self):
        admin = MagicMock()
        admin.execute.return_value.fetchone.return_value = (1,)
        with patch.object(pg.psycopg, 'connect') as connect, patch.object(pg, 'connect'), patch.object(pg.getpass, 'getpass', return_value='secret'):
            connect.return_value.__enter__.return_value = admin
            pg.provision({'url': 'postgresql://cmh_sms:secret@localhost/cmh_sms'})
        self.assertEqual(admin.execute.call_count, 2)
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in admin.execute.call_args_list))

    def test_copied_snapshot_settings_cannot_overwrite_legacy_sqlite(self):
        pg.save_config({'url': 'postgresql://app:secret@localhost/cmh_sms'})
        with patch.dict(os.environ, {'CMH_SMS_SQLITE_REPLICA': 'true',
                                    'CMH_SMS_SQLITE_REPLICA_PATH': 'data/cmh_sms.db'}):
            self.assertEqual(pg.environment()['CMH_SMS_SQLITE_REPLICA'], 'false')

    def test_module_launch_inherits_saved_postgres(self):
        pg.save_config({'url': 'postgresql://app:secret@localhost/cmh_sms'})
        with patch.object(pg.sys, 'argv', ['helper', 'alembic', 'upgrade', 'head']), patch.object(pg, 'connect'), patch.object(pg.subprocess, 'call', return_value=0) as launch:
            self.assertEqual(pg.main(), 0)
        self.assertEqual(launch.call_args.args[0][1:], ['-m', 'alembic', 'upgrade', 'head'])
        self.assertEqual(launch.call_args.kwargs['env']['CMH_SMS_DATABASE_MODE'], 'postgres')

    def test_server_exit_code_is_returned_to_supervisor(self):
        pg.save_config({'url': 'postgresql://app:secret@localhost/cmh_sms'})
        for code in (0, 1, 23):
            with self.subTest(code=code), patch.object(pg.sys, 'argv', ['helper', 'uvicorn', 'app.main:app']), \
                    patch.object(pg, 'connect'), patch.object(pg.subprocess, 'call', return_value=code):
                self.assertEqual(pg.main(), code)

    def test_database_outage_returns_failure_then_next_attempt_recovers(self):
        pg.save_config({'url': 'postgresql://app:private-password@localhost/cmh_sms'})
        with patch.object(pg.sys, 'argv', ['helper', 'uvicorn', 'app.main:app']), \
                patch.object(pg.subprocess, 'call', return_value=0) as launch:
            with patch.object(pg, 'connect', side_effect=pg.psycopg.OperationalError('private-password')), \
                    patch('builtins.print') as output:
                self.assertEqual(pg.main(), 1)
                launch.assert_not_called()
                self.assertNotIn('private-password', str(output.call_args_list))
            with patch.object(pg, 'connect'):
                self.assertEqual(pg.main(), 0)
                launch.assert_called_once()

    def test_missing_executable_returns_failure_without_leaking_credentials(self):
        pg.save_config({'url': 'postgresql://app:private-password@localhost/cmh_sms'})
        with patch.object(pg.sys, 'argv', ['helper', 'uvicorn', 'app.main:app']), \
                patch.object(pg, 'connect'), \
                patch.object(pg.subprocess, 'call', side_effect=OSError('private-password')), \
                patch('builtins.print') as output:
            self.assertEqual(pg.main(), 1)
            self.assertNotIn('private-password', str(output.call_args_list))

    def test_restart_reloads_saved_configuration(self):
        with patch.object(pg.sys, 'argv', ['helper', 'uvicorn', 'app.main:app']), \
                patch.object(pg, 'connect'), patch.object(pg.subprocess, 'call', return_value=0) as launch:
            for database in ('original', 'repaired'):
                pg.save_config({'url': f'postgresql://app:secret@localhost/{database}'})
                self.assertEqual(pg.main(), 0)
                self.assertTrue(launch.call_args.kwargs['env']['CMH_SMS_DATABASE_URL'].endswith('/' + database))


if __name__ == '__main__':
    unittest.main()
