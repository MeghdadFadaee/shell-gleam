import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import server_status as status
import install


class RendererTests(unittest.TestCase):
    def test_cache_fresh_stale_missing_and_actual_ubuntu_format(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'updates'
            self.assertTrue(status.update_status(cache, 48)[1])
            cache.write_text('Expanded Security Maintenance is not enabled.\n\n0 updates can be applied immediately.\n')
            self.assertFalse(status.update_status(cache, 48)[1])
            self.assertTrue(status.update_status(cache, 48, cache.stat().st_mtime + 49 * 3600)[1])
            cache.write_text('12 updates can be applied immediately.\n')
            self.assertIn('12 package', status.update_status(cache, 48)[0])
            cache.write_text('unknown output')
            self.assertIn('unknown', status.update_status(cache, 48)[0])

    def test_docker_health_is_not_invented(self):
        self.assertIn('no healthchecks', status.docker_status((0, 'web|running|Up 2 days'))[0])
        text, warning = status.docker_status((0, 'web|running|Up 2 days (healthy)\nworker|exited|Exited (1) 2 days ago'))
        self.assertTrue(warning)
        self.assertIn('1 failed', text)
        self.assertTrue(status.docker_status((-1, ''))[1])
        self.assertFalse(status.docker_status((0, 'job|exited|Exited (0) 1 day ago'))[1])

    def test_border_alignment_truncation_control_codes_and_ascii(self):
        cfg = dict(status.DEFAULTS, color=False)
        for ascii_mode in (False, True):
            cfg['ascii'] = ascii_mode
            output = status.box(cfg, '測試' * 60 + '\x1b[31m', 'Ubuntu', [('system', 'x' * 200, 'normal')], True)
            lines = [line for line in output.splitlines() if line]
            self.assertEqual({status.cells(line) for line in lines}, {76})
            self.assertNotIn('\x1b', output)
            if ascii_mode:
                output.encode('ascii')

    def test_invalid_configuration_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            for invalid in ({'width': 4}, {'command_timeout': 9}, {'services': [{'unit': '--help'}]}, {'sections': ['mystery']}, {'disk_warning': 95, 'disk_critical': 80}, {'color': 'yes'}, {'typo': True}, {'command_timeout': float('nan')}):
                path.write_text(json.dumps(invalid))
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    status.config(path)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.instance = install.Installation(self.root)
        self.instance.state.mkdir(parents=True)
        for name in install.PAM_FILES:
            pam = self.instance.path(name)
            pam.parent.mkdir(parents=True, exist_ok=True)
            pam.write_text('# authentication unchanged\n@include common-auth\nsession optional pam_motd.so motd=/run/motd.dynamic\nsession optional pam_motd.so noupdate\n')
        hooks = self.root / 'etc/update-motd.d'
        hooks.mkdir(parents=True)
        self.header = hooks / '00-header'
        self.header.write_text('#!/bin/sh\necho old\n')
        self.header.chmod(0o751)
        (hooks / '50-landscape').symlink_to('/usr/share/landscape/wrapper')
        # A relative executable symlink must be preserved as a symlink.
        (hooks / '10-link').symlink_to('00-header')
        (self.root / 'etc/motd').write_text('original static MOTD')

    def test_reinstall_new_package_hooks_and_uninstall_restore(self):
        self.instance.install(dict(status.DEFAULTS), False)
        self.assertIn(install.PAM_LINE, self.instance.path(install.PAM_FILES[0]).read_text())
        self.assertFalse(self.header.exists())
        self.assertTrue(Path(str(self.header) + install.SUFFIX).exists())
        config = self.instance.path(install.CONFIG)
        customized = dict(status.DEFAULTS, title='CUSTOM')
        config.write_text(json.dumps(customized))
        new_hook = self.root / 'etc/update-motd.d/90-new-package'
        new_hook.write_text('new')
        new_hook.chmod(0o755)
        self.instance.install(customized, False)
        self.assertEqual(json.loads(config.read_text())['title'], 'CUSTOM')
        self.assertFalse(new_hook.exists())
        self.instance.uninstall(False)
        for name in install.PAM_FILES:
            content = self.instance.path(name).read_text()
            self.assertIn('pam_motd.so motd=/run/motd.dynamic', content)
            self.assertNotIn('pam_exec.so', content)
            self.assertIn('@include common-auth', content)
        self.assertEqual(self.header.read_text(), '#!/bin/sh\necho old\n')
        self.assertEqual(self.header.stat().st_mode & 0o777, 0o751)
        self.assertEqual(os.readlink(self.root / 'etc/update-motd.d/10-link'), '00-header')
        self.assertEqual((self.root / 'etc/motd').read_text(), 'original static MOTD')
        self.assertTrue(new_hook.exists())
        self.assertFalse(self.instance.path(install.HOOK).exists())
        self.assertFalse(config.exists())
        self.instance.uninstall(False)

    @unittest.skipUnless(shutil.which('run-parts'), 'Debian run-parts unavailable')
    def test_pam_lsbsysinit_selects_only_managed_hook(self):
        self.instance.install(dict(status.DEFAULTS), False)
        selected = subprocess.check_output(['run-parts', '--lsbsysinit', '--test', str(self.root / 'etc/update-motd.d')], text=True)
        self.assertEqual(selected.splitlines(), [str(self.instance.path(install.HOOK))])

    def test_failure_restores_previous_files(self):
        real_atomic = install.atomic
        def fail_static(path, data, mode=0o644):
            if path == self.instance.path('/etc/motd'):
                raise OSError('simulated disk error')
            real_atomic(path, data, mode)
        with patch.object(install, 'atomic', fail_static), self.assertRaises(OSError):
            self.instance.install(dict(status.DEFAULTS), False)
        self.assertTrue(self.header.exists())
        self.assertEqual((self.root / 'etc/motd').read_text(), 'original static MOTD')
        self.assertFalse(self.instance.path(install.BINARY).exists())
        self.assertFalse(self.instance.manifest.exists())
        for name in install.PAM_FILES:
            self.assertIn('pam_motd.so motd=/run/motd.dynamic', self.instance.path(name).read_text())
            self.assertNotIn('pam_exec.so', self.instance.path(name).read_text())

    def test_dry_run_changes_nothing(self):
        self.instance.install(dict(status.DEFAULTS), True)
        self.assertTrue(self.header.exists())
        self.assertFalse(self.instance.manifest.exists())


if __name__ == '__main__':
    unittest.main()
