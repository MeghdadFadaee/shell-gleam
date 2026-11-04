#!/usr/bin/env python3
"""Build a static Pages site and reproducible, allowlisted installer payload."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES = (
    'setup.sh', 'deploy.sh', 'README.md', 'LICENSE', 'VERSION',
    'src/server_status.py', 'src/install.py', 'config/default.json',
    'docs/configuration.md', 'docs/operations.md',
)
ASSETS = ('index.html', 'style.css', 'app.js', 'favicon.svg', 'social.svg')


def build(output, site_url):
    output = Path(output).resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('output must not contain the source repository')
    output.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(ROOT / 'site' / name, output / name)
    (output / '.nojekyll').write_text('')
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as package:
            for name in sorted(PACKAGE_FILES):
                source = ROOT / name
                if source.is_symlink():
                    raise ValueError('payload cannot contain symlinks: ' + name)
                data = source.read_bytes()
                info = tarfile.TarInfo('shell-gleam/' + name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                info.mtime = 0
                package.addfile(info, io.BytesIO(data))
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    artifact = 'downloads/shell-gleam-' + digest[:16] + '.tar.gz'
    (output / 'downloads').mkdir(exist_ok=True)
    (output / artifact).write_bytes(data)
    (output / 'downloads/SHA256SUMS').write_text(digest + '  ' + Path(artifact).name + '\n')
    template = (ROOT / 'scripts/bootstrap.sh').read_text()
    installer = template.replace('@@SHA256@@', digest).replace('@@ARCHIVE@@', artifact).replace('@@SITE_URL@@', site_url.rstrip('/'))
    (output / 'setup.sh').write_text(installer)
    (output / 'setup.sh').chmod(0o755)
    manifest = {'name': 'shell-gleam', 'version': (ROOT / 'VERSION').read_text().strip(),
                'archive': artifact, 'sha256': digest, 'files': list(PACKAGE_FILES)}
    (output / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built ShellGleam site: ' + str(output))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    parser.add_argument('--site-url', default='https://meghdadfadaee.github.io/shell-gleam')
    args = parser.parse_args()
    build(args.output, args.site_url)
