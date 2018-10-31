import logging
import os
import subprocess

from deb.controlfile import ControlFile
from deb.controlfileparser import ControlFileParser
from momlib import md5sum
from util import tree


logger = logging.getLogger('debcontrolmerger')


# A class to merge Debian control files.
# It does not attempt a complete merge. Instead, it just executes a series
# of predefined strategies until the control files can be cleanly merged
# by diff3. These strategies will modify the left, right and base versions
# accordingly.
class DebControlMerger(object):
    def __init__(self, left_dir, left_name, right_dir, right_name, base_dir,
                 merged_dir):
        # Merge notes recorded here
        self.notes = []
        # If the merged file was modified (relative to the right version)
        self.modified = False

        self.left_name = left_name
        self.right_name = right_name

        self.left_dir = left_dir
        self.right_dir = right_dir
        self.base_dir = base_dir
        self.merged_dir = merged_dir

        control_path = 'debian/control'
        self.left_control_path = os.path.join(left_dir, control_path)
        self.right_control_path = os.path.join(right_dir, control_path)
        self.base_control_path = os.path.join(base_dir, control_path)
        self.merged_control_path = os.path.join(merged_dir, control_path)
        tree.ensure(self.merged_control_path)

        self.base_control = ControlFileParser(filename=self.base_control_path)
        self.left_control = ControlFileParser(filename=self.left_control_path)
        self.right_control = \
            ControlFileParser(filename=self.right_control_path)

        self.orig_right_md5sum = md5sum(self.right_control_path)

    def record_note(self, note, changelog_worthy=False):
        logger.debug(note)
        self.notes.append((note, changelog_worthy))

    def do_diff3(self):
        rc = subprocess.call(("diff3", "-E", "-m",
                              "-L", self.left_name, self.left_control_path,
                              "-L", "BASE", self.base_control_path,
                              "-L", self.right_name, self.right_control_path),
                             stdout=open(self.merged_control_path, 'w'))
        if rc != 0:
            return False

        self.modified = \
            md5sum(self.merged_control_path) != self.orig_right_md5sum
        return True

    def run(self):
        if self.do_diff3():
            return True

        merge_funcs = (
            (self.merge_uploaders, ()),
            (self.merge_paragraphs, ()),
        )

        # Try all the merge strategies until diff3 is happy
        for func, args in merge_funcs:
            func(*args)
            if self.do_diff3():
                return True

        return False

    # Drop Uploaders changes from the left side as they are irrelevant and
    # just generate merge noise.
    def merge_uploaders(self):
        left_para0 = self.left_control.parse()[0]
        base_para0 = self.base_control.parse()[0]

        # See if we've modified Uploaders in our version
        base_uploaders = base_para0.get('Uploaders')
        if base_uploaders == left_para0.get('Uploaders'):
            return

        # If so, rewrite our own control file with the original Uploaders
        logging.debug('Restoring Uploaders to base value to see if it helps '
                      'with conflict resolution')
        left_control.patch(None, 'Uploaders', base_uploaders)
        left_control.write()
        self.record_note('Dropped uninteresting Uploaders change')

    def merge_paragraph(self, package):
        base_para = self.base_control.get_paragraph(package)
        left_para = self.left_control.get_paragraph(package)
        right_para = self.right_control.get_paragraph(package)

        added_fields = set(left_para.keys()) - set(base_para.keys())
        if right_para is not None:
            added_fields -= set(right_para.keys())
        else:
            added_fields.clear()

        for field in added_fields:
            self.right_control.add_field(package, field, left_para[field])
            self.right_control.write()

            # Remove the field from left version to ease the merge
            self.left_control.remove_field(package, field)
            self.left_control.write()

            self.record_note('Readded %s %s' % (package or '', field))

    # Perform simple merge operations on paragraphs and their contents
    def merge_paragraphs(self):
        self.merge_paragraph(None)

        for pkg in self.base_control.get_package_names():
            if self.left_control.get_paragraph(pkg):
                self.merge_paragraph(pkg)
                continue

            logger.debug('Carrying forward %s package removal', pkg)

            # Package was removed on left, so remove it on the right
            self.right_control.remove_package(pkg)
            self.right_control.write()

            # To ease the merge, also remove it from the base version
            self.base_control.remove_package(pkg)
            self.base_control.write()

            self.record_note('Carried forward removal of %s binary package '
                             % pkg)

        for pkg in self.left_control.get_package_names():
            if self.base_control.get_paragraph(pkg):
                continue

            logger.debug('Carrying forward %s package addition', pkg)
            para = self.left_control.get_paragraph(pkg)

            # Package was added on left, so add it on the right
            self.right_control.add_paragraph(unicode(para))
            self.right_control.write()

            # To ease the merge, drop the package addition from the left
            self.left_control.remove_package(pkg)
            self.left_control.write()

            self.record_note('Carried forward addition of %s binary package'
                             % pkg)
