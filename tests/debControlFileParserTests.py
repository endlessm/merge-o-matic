from tempfile import NamedTemporaryFile
import unittest

from deb.controlfileparser import ControlFileParser


class ControlFileParserTest(unittest.TestCase):
    def test_uploadersOneLine(self):
        controlfile = """Source: cheese
Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@debian.org>
Uploaders: Mr Frog <frog@frog.com>, James <james@foo.com>
Build-Depends: debhelper (>= 11)
"""

        parser = ControlFileParser(text=controlfile)
        parser.patch('Uploaders', 'new <one@two.com>')
        new = parser.get_text()

        self.assertEqual(new, """Source: cheese
Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@debian.org>
Uploaders: new <one@two.com>
Build-Depends: debhelper (>= 11)
""")
