import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts.prepare_public_notebooks import public_links
from scripts.setup_research import install_bundle, safe_member


def test_public_metrics_link_has_repository_destination():
    html = '<a href="../reports/tables/raw_momentum_6m_equal_weight_all_return_layer_metrics.csv">Metrics</a>'
    assert '../results/' in public_links(html)
    assert '../reports/' not in public_links(html)


def test_archive_rejects_traversal_and_links():
    member = tarfile.TarInfo('../secret')
    assert not safe_member(member, {'../secret': {'bytes': 0}})
    member = tarfile.TarInfo('data/processed/a.csv')
    member.type = tarfile.SYMTYPE
    assert not safe_member(member, {member.name: {'bytes': 0}})


def test_bundle_verified_and_existing_changes_preserved(tmp_path):
    archive = tmp_path / 'test.tar.gz'
    name, data = 'data/processed/example.csv', b'value\n1\n'
    with tarfile.open(archive, 'w:gz') as output:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        output.addfile(info, io.BytesIO(data))
    manifest = {'bytes': archive.stat().st_size,
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
    root = tmp_path / 'checkout'
    root.mkdir()
    install_bundle(archive, manifest, root)
    assert (root / name).read_bytes() == data
    install_bundle(archive, manifest, root)
    (root / name).write_text('changed')
    with pytest.raises(ValueError, match='preserved'):
        install_bundle(archive, manifest, root)
    assert (root / name).read_text() == 'changed'
    manifest['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='checksum'):
        install_bundle(archive, manifest, root)


def test_published_notebooks_have_fallbacks_and_no_broken_report_links():
    root = Path(__file__).resolve().parents[1]
    books = sorted((root / 'notebooks').glob('*.ipynb'))
    assert len(books) == 23
    count = 0
    for path in books:
        for cell in json.loads(path.read_text())['cells']:
            for output in cell.get('outputs', []):
                data = output.get('data', {})
                if 'application/vnd.plotly.v1+json' in data:
                    assert base64.b64decode(data['image/png']).startswith(b'\x89PNG\r\n\x1a\n')
                    count += 1
                html = ''.join(data.get('text/html', []))
                assert 'href="../reports/tables/' not in html
    assert count == 191
