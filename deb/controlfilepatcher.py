#!/usr/bin/env python
from __future__ import with_statement

import gzip


class ControlFilePatcher(object):
    def __init__(self, text=None, filename=None, fd=None):
        if text:
            self.text = text
        elif filename:
            if filename[-3:] == ".gz":
                with gzip.open(filename) as gzf:
                    self.text = gzf.read()
            else:
                with open(filename) as f:
                    self.text = f.read()
        elif fd:
            self.text = f.read()
        else:
            raise Exception("No input provided")

    def capitaliseField(self, field):
        return "-".join([w.title() for w in field.split("-")])

    def patch(self, search_field, new_value):
        last_field = None
        para_border = True

        output = ''
        text = self.text
        if text.endswith("\n"):
            text = text[:-1]
        lines = text.split('\n')

        for i in range(len(lines)):
            line = lines[i]

            if line.startswith("#"):
                output += line + "\n"
                continue

            # Multiple blank lines are permitted at paragraph borders
            if not len(line) and para_border:
                output += "\n"
                continue
            para_border = False

            if line[:1].isspace():
                if last_field is None:
                    raise IOError
                if last_field == search_field:
                    continue

            elif ":" in line:
                (field, value) = line.split(":", 1)
                if len(field.rstrip().split(None)) > 1:
                    raise IOError

                last_field = self.capitaliseField(field)
                if last_field == search_field:
                    output += "%s: %s\n" % (search_field, new_value)
                    continue

            elif not len(line):
                para_border = True
                last_field = None

            else:
                raise IOError

            output += line + "\n"

        self.text = output

    def get_text(self):
        return self.text
