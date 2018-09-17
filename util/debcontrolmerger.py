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
