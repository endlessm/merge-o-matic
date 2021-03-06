#!/usr/bin/env python
from __future__ import with_statement

from collections import OrderedDict
import gzip
import os

from lark import Lark
from lark.lexer import Token
from lark.visitors import Transformer_InPlace, v_args


my_dir = os.path.dirname(os.path.abspath(__file__))
control_parser = Lark.open(os.path.join(my_dir, 'controlfile.lark'),
                           parser='lalr', propagate_positions=True)

# Dependency list parser.
# It should be possible to combine this into control_parser, but it's tricky.
# We would have to assign priorities, but the LALR parser doesn't support
# that, and we need LALR to have the end line/column info available.
# Even with the dynamic parser I couldn't get it to reliably follow the
# stated priorties.
# To get around the difficulties, we parse dependency lists separately.
deplist_parser = Lark.open(os.path.join(my_dir, 'deplist.lark'),
                           parser='lalr', propagate_positions=True)


# A class to represent the position of a string token inside a larger
# text.
# start_line: Starting line offset within the text. First line is line 1.
# start_char: Starting character offset within the line. First char is char 1.
# end_line: Ending line offset within the text.
# end_char: Ending character offset within the text.
#
# end_line and end_char point at the final character of the token, e.g.
# a token with length 1 will have the same start and end.
class StringPosition(object):
    def __init__(self, start_line, start_char, end_line, end_char):
        self.start_line = start_line
        self.start_char = start_char
        self.end_line = end_line
        self.end_char = end_char

    def __repr__(self):
        return '<%s %d %d %d %d>' % (self.__class__.__name__,
                                     self.start_line, self.start_char,
                                     self.end_line, self.end_char)

    def __eq__(self, other):
        return self.start_line == other.start_line \
            and self.start_char == other.start_char \
            and self.end_line == other.end_line \
            and self.end_char == other.end_char

    def offset(self, other):
        self.start_line += other.start_line - 1
        self.start_char += other.start_char - 1
        self.end_line += other.start_line - 1
        self.end_char += other.start_char - 1

    def decrement_end(self, original_text):
        self.end_char -= 1
        if self.end_char == 0:
            self.end_line -= 1
            self.end_char = \
                len(original_text.split('\n')[self.end_line - 1]) + 1

    @staticmethod
    def from_token(token, original_text, drop_newline=False):
        ret = StringPosition(token.line, token.column,
                             token.end_line, token.end_column)

        if drop_newline:
            ret.decrement_end(original_text)

        # Lark's end_column generally points at the first character of
        # the following token, we tweak it to point at the last character
        # of this token.
        ret.decrement_end(original_text)
        return ret

    # Get the StringPosition that corresponds to a Tree
    @staticmethod
    def from_tree(tree, original_text):
        pos = StringPosition(tree.line, tree.column,
                             tree.end_line, tree.end_column)

        # I can't find a way for the grammar to accept this and still
        # pass our tests, but the newline should be excluded from
        # the following token types. Exclude it here instead.
        if tree.data in ('field', 'data'):
            pos.decrement_end(original_text)

        # Lark's end_column generally points at the first character of
        # the following token, we tweak it to point at the last character
        # of this token.
        pos.decrement_end(original_text)
        return pos


# A class to represent a substring of a larger body of text.
# It's just a string with an attached "position" property that details
# where it was located in the original text.
class StrWithPos(unicode):
    def __new__(self, value, position):
        return unicode.__new__(self, value)

    def __init__(self, value, position):
        self.position = position


# A class to represent a dictionary that also has an attached "position"
# property that details where it was located in the original text.
class Paragraph(dict):
    def __new__(self, control_file, position):
        return dict.__new__(self)

    def __init__(self, control_file, position):
        self.position = position
        self.control_file = control_file

    def __unicode__(self):
        return self.control_file.text_at_position(self.position)


# A class to represent a dependency (e.g. an item in Build-Depends)
class Dependency(object):
    def __init__(self, dependency_list, parent_token, token):
        self.dependency_list = dependency_list
        self.name = token.children[0].children[0]
        self.version_constraint = None
        self.arch_list = None
        self.position = StringPosition.from_tree(token, parent_token)
        self.position.offset(parent_token.position)

        for child in token.children:
            if child.data == "version_constraint":
                token = child.children[0]
                position = StringPosition.from_token(token, parent_token)
                position.offset(parent_token.position)
                self.version_constraint = StrWithPos(token, position)
            elif child.data == "arch_list":
                self.arch_list = child.children[0]

    def __eq__(self, other):
        return self.name == other.name \
            and self.version_constraint == other.version_constraint \
            and self.arch_list == other.arch_list

    def __unicode__(self):
        return \
            self.dependency_list.control_file.text_at_position(self.position)

    def __str__(self):
        return self.__unicode__()

    def __repr__(self):
        return '<%s %s %s %s>' % (self.__class__.__name__, self.name,
                                  self.version_constraint, self.arch_list)


# A class to represent the Depends/Build-Depends field of a control file
# (i.e. a group of dependencies).
# It's an ordered dictionary, the dependencies are in order that they
# appear in the file.
class DependencyList(OrderedDict):
    def __init__(self, control_file, values):
        super(DependencyList, self).__init__()

        self.control_file = control_file
        for part in values:
            deps = deplist_parser.parse(part)
            for or_dep in deps.children:
                for dep_token in or_dep.children:
                    dep = Dependency(self, part, dep_token)
                    self[dep.name] = dep


# A value of a control field.
# Represented as a class because the parser deals with multiple values per
# field, as a value can be separated onto multiple lines.
class FieldValue(object):
    def __init__(self, tree, parser):
        self.parser = parser

        self.values = []
        for token in tree.children:
            value = StrWithPos(token,
                               StringPosition.from_token(token, parser.text))
            self.values.append(value)

        self.position = StringPosition.from_tree(tree, parser.text)

    def __unicode__(self):
        return self.parser.text_at_position(self.position)

    def __str__(self):
        return self.__unicode__()

    def __eq__(self, other):
        return unicode(self) == other

    def __ne__(self, other):
        return not self.__eq__(other)


# Make the parse tree easier to work with
class ControlFileTransformer(Transformer_InPlace):
    def __init__(self, parser):
        self.parser = parser

    # Replace name trees with StrWithPos
    def name(self, (token,)):
        return StrWithPos(token,
                          StringPosition.from_token(token, self.parser.text))

    # Replac values with FieldValue
    @v_args(tree=True)
    def data(self, tree):
        return FieldValue(tree, self.parser)

    # Replace paragraphs with dictionaries
    @v_args(tree=True)
    def para(self, tree):
        ret = Paragraph(self.parser,
                        StringPosition.from_tree(tree, self.parser.text))
        for field in tree.children:
            ret[field.children[0]] = field.children[1]

        return ret

    # Work with a simple list of paragraphs at the top-level
    def start(self, items):
        return items


class ControlFileParser(object):
    def __init__(self, text=None, filename=None, fd=None):
        if text:
            self.text = text.decode('utf-8')
        elif filename:
            self.filename = filename
            if filename[-3:] == ".gz":
                with gzip.open(filename) as gzf:
                    self.text = gzf.read().decode('utf-8')
            else:
                with open(filename) as f:
                    self.text = f.read().decode('utf-8')
        elif fd:
            self.text = f.read().decode('utf-8')
        else:
            raise Exception("No input provided")

        # Paragraphs are normally separated by empty lines, however it's
        # also permitted to have whitespace on that separating line.
        # This is hard to parse with LALR, so we catch those lines and
        # remove the extra whitespace.
        lines = self.text.splitlines(True)
        for i, line in enumerate(lines):
            if len(line) > 1 and line[:-1].isspace():
                lines[i] = line.strip() + '\n'
        self.text = "".join(lines)

    def write(self):
        with open(self.filename, "w") as new_control:
            new_control.write(self.get_text().encode('utf-8'))
            new_control.flush()

    def parse(self):
        result = control_parser.parse(self.text)
        return ControlFileTransformer(self).transform(result)

    # Return a paragraph corresponding to a given Package
    # Pass package=None for paragraph 0 (the Source paragraph)
    def get_paragraph(self, package):
        paras = self.parse()
        if not package:
            return paras[0]
        for para in paras:
            if 'Package' in para and para['Package'] == package:
                return para
        return None

    def get_package_names(self):
        paras = self.parse()
        return [unicode(para['Package'])
                for para in paras if 'Package' in para]

    def parse_depends(self, package, search_field):
        para = self.get_paragraph(package)
        if search_field in para:
            return DependencyList(self, para[search_field].values)

        return {}

    # Extract the text at the given position
    def text_at_position(self, position):
        lines = self.text.splitlines(True)
        if position.start_line == position.end_line:
            return lines[position.start_line - 1][position.start_char - 1:
                                                  position.end_char]

        output = lines[position.start_line - 1][position.start_char - 1:]
        for i in range(position.start_line, position.end_line - 1):
            output += lines[i]
        output += lines[position.end_line - 1][0:position.end_char]
        return output

    # Replace the text currently at the given StringPosition with the new
    # value provided.
    def patch_at_offset(self, position, new_value):
        lines = self.text.split("\n")
        output = ''

        # Copy leading lines verbatim
        for i in range(0, position.start_line - 1):
            output += lines[i]
            output += '\n'

        # On the modified line, copy the leading unmodified characters
        output += lines[position.start_line - 1][0:position.start_char - 1]
        # and insert the new value
        output += unicode(new_value)
        # add the remainder of the original line
        if position.end_char == 1:
            output += '\n'
        output += lines[position.end_line - 1][position.end_char:]
        output += '\n'

        # Now copy the following lines verbatim
        for i in range(position.end_line, len(lines) - 1):
            output += lines[i]
            output += '\n'

        self.text = output

    def insert_lines(self, start_line, text):
        lines = self.text.split("\n")
        output = ''

        # Copy leading lines
        for i in range(0, start_line - 1):
            output += lines[i]
            output += '\n'

        output += text

        # Copy following lines
        for i in range(start_line - 1, len(lines) - 1):
            output += lines[i]
            output += '\n'

        self.text = output

    def remove_lines(self, start_line, end_line):
        lines = self.text.split("\n")
        output = ''

        # Copy leading lines
        for i in range(0, start_line - 1):
            output += lines[i]
            output += '\n'

        # Copy following lines
        for i in range(end_line, len(lines) - 1):
            output += lines[i]
            output += '\n'

        self.text = output

    def remove_field(self, package, search_field):
        para = self.get_paragraph(package)
        if search_field not in para:
            return

        self.remove_lines(para[search_field].position.start_line,
                          para[search_field].position.end_line)

    def remove_package(self, package):
        para = self.get_paragraph(package)
        if not para:
            return

        # Package paragraphs are separated by blank lines. When removing
        # the paragraph, remove the preceding blank line too.
        self.remove_lines(para.position.start_line - 1, para.position.end_line)

    def patch(self, package, search_field, new_value):
        para = self.get_paragraph(package)
        if para is None or search_field not in para:
            return False

        self.patch_at_offset(para[search_field].position, new_value)
        return True

    def add_paragraph(self, value):
        self.text += "\n"
        self.text += value

    def add_field(self, package, field, value):
        para = self.get_paragraph(package)
        text = "%s: %s\n" % (field, value)
        self.insert_lines(para.position.end_line + 1, text)

    def __remove_list_entry(self, position):
        lines = self.text.split("\n")
        start_line = lines[position.start_line - 1]
        start_char = position.start_char
        end_line = lines[position.end_line - 1]
        end_char = position.end_char

        # If this is the right-hand side of an OR, drop the | but preserve
        # any following comma.
        if start_line[start_char - 4:start_char - 1] == ' | ':
            start_char -= 3
        # If followed by a comma, remove that too
        elif len(end_line) > end_char and end_line[end_char] == ',':
            end_char += 1

        # If followed by whitespace, remove that too
        while len(end_line) > end_char and end_line[end_char].isspace():
            end_char += 1

        # If this is the left-hand side of an OR, drop the | and any following
        # whitespace.
        if len(end_line) > end_char and end_line[end_char] == '|':
            end_char += 1
            while len(end_line) > end_char and end_line[end_char].isspace():
                end_char += 1

        position.start_char = start_char
        position.end_char = end_char

        # If everything else on the line is empty or whitespace, then just
        # remove the whole line
        prefix = end_line[0:position.start_char - 1]
        suffix = end_line[position.end_char:]
        if (len(prefix) == 0 or prefix.isspace()) \
                and (len(suffix) == 0 or suffix.isspace()):
            output = []
            output.extend(lines[0:position.start_line - 1])
            output.extend(lines[position.end_line:])
            self.text = "\n".join(output)
            return

        # If we're removing the final entry on a line, remove any preceding
        # space
        if len(suffix) == 0 and start_char > 1 \
                and not start_line[:start_char - 1].isspace() \
                and start_line[start_char - 2].isspace():
            position.start_char -= 1

        # Patch the entry out
        self.patch_at_offset(position, '')

    def remove_depends_entry(self, package, field, entry):
        deps = self.parse_depends(package, field)
        if entry not in deps:
            return

        if len(deps) == 1:
            self.remove_field(package, field)
            return

        self.__remove_list_entry(deps[entry].position)

    def add_depends_entry(self, package, field, entry):
        para = self.get_paragraph(package)
        if field not in para:
            self.add_field(package, field, entry)
            return

        current_value = para[field]
        new_value = unicode(current_value)

        if not new_value.endswith(','):
            new_value += ','

        if '\n' in new_value:
            new_value += "\n " + entry
        else:
            new_value += ' ' + entry

        self.patch_at_offset(current_value.position, new_value)

    def get_text(self):
        return self.text
