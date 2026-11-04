import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_site', ROOT / 'scripts/build_site.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    def test_reproducible_payload_exact_allowlist_and_rendered_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = builder.build(root / 'first', 'https://example.github.io/shell-gleam')
            second = builder.build(root / 'second', 'https://example.github.io/shell-gleam')
            self.assertEqual(first, second)
            archive = root / 'first' / first['archive']
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), first['sha256'])
            with tarfile.open(archive) as package:
                self.assertEqual(set(package.getnames()), {'shell-gleam/' + name for name in builder.PACKAGE_FILES})
                self.assertTrue(all(member.isfile() for member in package))
            bootstrap = (root / 'first/setup.sh').read_text()
            self.assertNotIn('@@', bootstrap)
            self.assertIn(first['sha256'], bootstrap)
            self.assertIn('https://example.github.io/shell-gleam', bootstrap)
            subprocess.run(['bash', '-n', str(root / 'first/setup.sh')], check=True)

    def test_unlisted_local_file_never_enters_package(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'source'
            for name in (*builder.PACKAGE_FILES, 'scripts/bootstrap.sh', *('site/' + a for a in builder.ASSETS)):
                destination = fixture / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            (fixture / 'config/local-secret.json').write_text('{"token":"do-not-package"}')
            with patch.object(builder, 'ROOT', fixture):
                release = builder.build(Path(directory) / 'output', 'https://example.github.io/shell-gleam')
            with tarfile.open(Path(directory) / 'output' / release['archive']) as package:
                self.assertFalse(any('local-secret' in name for name in package.getnames()))

    def test_custom_domain_updates_all_public_install_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            release = builder.build(output, 'http://status.example.org/tools/shell-gleam/')
            canonical = 'https://status.example.org/tools/shell-gleam'
            self.assertEqual(release['site_url'], canonical)
            for name in ('index.html', 'app.js', 'setup.sh'):
                text = (output / name).read_text()
                self.assertIn(canonical, text)
                self.assertNotIn(builder.DEFAULT_SITE_URL, text)

    def test_invalid_site_url_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            for url in ('file:///etc', 'https://example.org/\';touch', 'https://example.org/\nnext'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    builder.build(output, url)
            self.assertFalse(output.exists())

    def test_source_root_cannot_be_output(self):
        with self.assertRaises(ValueError):
            builder.build(ROOT, 'https://example.github.io/shell-gleam')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.tmp = self.root / 'tmp'
        self.tmp.mkdir()
        self.archive = self.root / 'payload.tar.gz'
        for name, content in {
            'id': '#!/bin/sh\necho 0\n',
            'curl': '#!/usr/bin/env python3\nimport os,shutil,sys\nif os.environ.get("TEST_CURL_FAIL"): sys.exit(22)\nshutil.copyfile(os.environ["TEST_ARCHIVE"], sys.argv[sys.argv.index("-o")+1])\n',
        }.items():
            path = self.bin / name
            path.write_text(content)
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'TEST_ARCHIVE': str(self.archive), 'TMPDIR': str(self.tmp),
                    'SHELL_GLEAM_BASE_URL': 'http://127.0.0.1:8000'}

    def package(self, name='shell-gleam/setup.sh', symlink=False):
        with tarfile.open(self.archive, 'w:gz') as package:
            data = b'#!/bin/sh\nprintf "ARG=<%s>\\n" "$@"\n'
            member = tarfile.TarInfo(name)
            member.mode = 0o755
            if symlink:
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
                package.addfile(member)
            else:
                member.size = len(data)
                package.addfile(member, io.BytesIO(data))

    def run_bootstrap(self, *args, wrong_checksum=False):
        checksum = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        template = (ROOT / 'scripts/bootstrap.sh').read_text()
        script = template.replace('@@SHA256@@', '0' * 64 if wrong_checksum else checksum).replace('@@ARCHIVE@@', 'downloads/test.tar.gz').replace('@@SITE_URL@@', 'https://example.github.io/shell-gleam')
        return subprocess.run(['bash', '-s', '--', *args], input=script, capture_output=True, text=True, env=self.env)

    def test_piped_execution_argument_forwarding_and_cleanup(self):
        self.package()
        result = self.run_bootstrap('install', '--dry-run', '--title', "O'Brien $(touch nope); *")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARG=<O'Brien $(touch nope); *>", result.stdout)
        self.assertIn('SHA-256 verified', result.stdout)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_checksum_failure_stops_before_setup(self):
        self.package()
        result = self.run_bootstrap('--dry-run', wrong_checksum=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertNotIn('ARG=', result.stdout)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_traversal_and_symlinks_rejected(self):
        for name, symlink in [('shell-gleam/../../escape', False), ('shell-gleam/link', True)]:
            with self.subTest(name=name):
                self.package(name, symlink)
                result = self.run_bootstrap('--dry-run')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unsafe package', result.stderr)
                self.assertFalse((self.root / 'escape').exists())

    def test_download_failure_stops_before_setup(self):
        self.package()
        self.env['TEST_CURL_FAIL'] = '1'
        result = self.run_bootstrap('--dry-run')
        self.assertEqual(result.returncode, 22)
        self.assertNotIn('ARG=', result.stdout)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_non_https_remote_override_rejected(self):
        self.package()
        self.env['SHELL_GLEAM_BASE_URL'] = 'http://example.com'
        result = self.run_bootstrap('--dry-run')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must use HTTPS', result.stderr)


if __name__ == '__main__':
    unittest.main()
