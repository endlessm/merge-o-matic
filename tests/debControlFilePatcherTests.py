from tempfile import NamedTemporaryFile
import unittest

from deb.controlfilepatcher import ControlFilePatcher


class ControlFilePatcherTest(unittest.TestCase):
    def test_uploaders_oneline(self):
        controlfile = """Source: cheese
Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@debian.org>
Uploaders: Mr Frog <frog@frog.com>, James <james@foo.com>
Build-Depends: debhelper (>= 11)
"""

        patcher = ControlFilePatcher(text=controlfile)
        patcher.patch('Uploaders', 'new <one@two.com>')
        new = patcher.get_text()

        self.assertEqual(new, """Source: cheese
Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@debian.org>
Uploaders: new <one@two.com>
Build-Depends: debhelper (>= 11)
""")
