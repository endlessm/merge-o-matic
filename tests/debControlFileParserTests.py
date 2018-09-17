# coding=utf-8

from tempfile import NamedTemporaryFile
import unittest

from deb.controlfileparser import ControlFileParser, StringPosition


class ControlFileParserTest(unittest.TestCase):
    # Test parsing of control syntax elements
    def test_parse(self):
        controlfile = \
            "# A comment\n" \
            "#\n" \
            "Source: foo\n" \
            "Uploaders:\n" \
            " ä <a@a.com>,\n" \
            " b <b@b.com>\n"
        parser = ControlFileParser(text=controlfile)
        parser.parse()

    # Test control files that have an extra newline at the end
    def test_parseExtraNewline(self):
        controlfile = \
            "Source: foo\n" \
            "Uploaders:\n" \
            " a <a@a.com>,\n" \
            " b <b@b.com>\n" \
            "\n"
        parser = ControlFileParser(text=controlfile)
        parser.parse()

    # Test control files that have multiple newlines between packages
    def test_parseMultiNewline(self):
        controlfile = \
            "Source: foo\n" \
            "Uploaders: a <a@a.com>\n" \
            "\n" \
            "Package: foo1\n" \
            "\n" \
            "\n" \
            "Package: foo2\n"
        ControlFileParser(text=controlfile).parse()

    # Test control files that have spaces on the blank line that separates
    # paragraphs
    def test_parseSpaceSeparation(self):
        controlfile = \
            "Source: foo\n" \
            "Uploaders: a <a@a.com>\n" \
            "\n" \
            "Package: foo1\n" \
            " \n" \
            "Package: foo2\n"
        ControlFileParser(text=controlfile).parse()

    # Test StringPosition calculations
    def test_stringPositions(self):
        text = \
            "Source: foo\n" \
            "Build-Depends: aa (> 3),\n" \
            " bb,\n" \
            "Uploaders: a <a@a.com>, <b@b.com>\n" \
            "\n" \
            "Package: foo\n" \
            "Suggests: bar\n"

        parser = ControlFileParser(text=text)
        result = parser.parse()
        para0 = result[0]
        para1 = result[1]

        self.assertEqual(StringPosition(1, 9, 1, 11),
                         para0['Source'].position)
        self.assertEqual(StringPosition(2, 16, 3, 4),
                         para0['Build-Depends'].position)
        self.assertEqual(StringPosition(4, 12, 4, 33),
                         para0['Uploaders'].position)

        self.assertEqual(StringPosition(1, 1, 4, 34), para0.position)
        self.assertEqual(StringPosition(6, 1, 7, 14), para1.position)

    def test_getParagraph(self):
        text = \
            "Source: foo\n" \
            "\n" \
            "Package: one\n" \
            "Architecture: amd64\n" \
            "\n" \
            "Package: two\n" \
            "Architecture: armhf\n"

        parser = ControlFileParser(text=text)
        self.assertIsNotNone(parser.get_paragraph(None))
        self.assertIsNotNone(parser.get_paragraph("one"))
        self.assertIsNotNone(parser.get_paragraph("two"))
        self.assertIsNone(parser.get_paragraph("three"))
        self.assertEqual(unicode(parser.get_paragraph("one")),
                         "Package: one\n"
                         "Architecture: amd64\n")

    def test_getFieldValue(self):
        text = \
            "Source: foo\n" \
            "\n" \
            "Package: one\n" \
            "Architecture: amd64\n"

        parser = ControlFileParser(text=text)
        para0 = parser.get_paragraph(None)
        one = parser.get_paragraph("one")

        self.assertEqual("foo", para0['Source'])
        self.assertEqual("amd64", one['Architecture'])

    # Test that we can replace the Uploaders field.
    # The original field is on a single line.
    def test_uploadersOneLine(self):
        controlfile = \
            "Source: cheese\n" \
            "Maintainer: GNOME <gnome@debian.org>\n" \
            "Uploaders: Frog <frog@frog.com>, James <james@foo.com>\n" \
            "Build-Depends: debhelper (>= 11)\n"

        parser = ControlFileParser(text=controlfile)
        parser.patch(None, 'Uploaders', 'new <one@two.com>')
        new = parser.get_text()

        self.assertEqual(new,
                         "Source: cheese\n"
                         "Maintainer: GNOME <gnome@debian.org>\n"
                         "Uploaders: new <one@two.com>\n"
                         "Build-Depends: debhelper (>= 11)\n")

    # Test that we can replace the Uploaders field.
    # The original field is on multiple lines.
    def test_uploadersMultiLine(self):
        controlfile = \
            "Source: cheese\n" \
            "Maintainer: GNOME <gnome@debian.org>\n" \
            "Uploaders: Frog <frog@frog.com>,\n" \
            " James <james@foo.com>\n" \
            "Build-Depends: debhelper (>= 11)\n"

        parser = ControlFileParser(text=controlfile)
        parser.patch(None, 'Uploaders', 'new <one@two.com>')
        new = parser.get_text()

        self.assertEqual(new,
                         "Source: cheese\n"
                         "Maintainer: GNOME <gnome@debian.org>\n"
                         "Uploaders: new <one@two.com>\n"
                         "Build-Depends: debhelper (>= 11)\n")

    def test_removePackage(self):
        controlfile = \
            "Source: foo\n" \
            "Build-Depends: bar\n" \
            "\n" \
            "Package: foo1\n" \
            "Suggests: something\n" \
            "\n" \
            "Package: foo2\n" \
            "Suggests: something\n" \
            "\n" \
            "Package: foo3\n" \
            "Suggests: something\n" \
            "\n" \
            "Package: foo4\n" \
            "Suggests: something\n"

        parser = ControlFileParser(text=controlfile)
        parser.remove_package('foo1')
        parser.remove_package('foo2')
        parser.remove_package('foo4')
        self.assertEqual(parser.get_text(),
                         "Source: foo\n"
                         "Build-Depends: bar\n"
                         "\n"
                         "Package: foo3\n"
                         "Suggests: something\n")

    def test_addParagraph(self):
        controlfile = \
            "Source: foo\n" \
            "Build-Depends: bar\n"

        parser = ControlFileParser(text=controlfile)
        parser.add_paragraph("Package: mypkg\n"
                             "Suggests: gcc\n")
        self.assertIsNotNone(parser.get_paragraph("mypkg"))
        self.assertEqual(parser.get_text(),
                         "Source: foo\n"
                         "Build-Depends: bar\n"
                         "\n"
                         "Package: mypkg\n"
                         "Suggests: gcc\n")

    def test_addField(self):
        controlfile = \
            "Source: foo\n" \
            "Build-Depends: bar\n" \
            "\n" \
            "Package: foo1\n" \
            "Suggests: something\n" \
            "\n" \
            "Package: foo2\n" \
            "Suggests: something\n"

        parser = ControlFileParser(text=controlfile)
        parser.add_field('foo1', 'X-Something', 'asdf')
        self.assertEqual(parser.get_text(),
                         "Source: foo\n"
                         "Build-Depends: bar\n"
                         "\n"
                         "Package: foo1\n"
                         "Suggests: something\n"
                         "X-Something: asdf\n"
                         "\n"
                         "Package: foo2\n"
                         "Suggests: something\n")
