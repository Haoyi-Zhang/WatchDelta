"""Portable retained-byte checks at paths exceeding the Windows legacy limit."""
import hashlib
from contextlib import contextmanager
from pathlib import Path
import tempfile

from watchdelta.core import digest, projection, readable_tree, source_fingerprint

@contextmanager
def scratch():
    temporary = tempfile.TemporaryDirectory()
    ordinary_root = Path(temporary.name)
    # The fixture cleanup must traverse the same deep paths on Windows.
    temporary.name = str(readable_tree(ordinary_root))
    with temporary:
        yield ordinary_root


def test_deep_projection_preserves_relative_names_and_all_bytes():
    with scratch() as directory:
        root = Path(directory).joinpath(*('retained-' + str(i) + '-' + 'x' * 35 for i in range(7)))
        extended = readable_tree(root)
        extended.mkdir(parents=True)
        (extended / 'index.html').write_bytes(b'owned terminal bytes\r\n')
        (extended / 'extra.html').write_bytes(b'owned extra path')
        assert len(str(root / 'index.html')) > 300
        assert projection(root, '.html') == {
            'index.html': digest(b'owned terminal bytes\r\n'),
            'extra.html': digest(b'owned extra path')}


def test_deep_source_identity_uses_relative_paths_not_installation_prefix():
    with scratch() as directory:
        root = Path(directory).joinpath(*('source-' + str(i) + '-' + 'x' * 35 for i in range(7)))
        extended = readable_tree(root)
        (extended / 'src/nested').mkdir(parents=True)
        data = b'owned source bytes\r\n'
        (extended / 'src/nested/index.md').write_bytes(data)
        name = b'src/nested/index.md'
        expected = hashlib.sha256(len(name).to_bytes(8, 'big') + name +
                                  len(data).to_bytes(8, 'big') + data).hexdigest()
        assert source_fingerprint(root, 'docs') == (expected, len(data))
        assert source_fingerprint(extended, 'docs') == (expected, len(data))
