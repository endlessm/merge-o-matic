import logging
import os
import subprocess

from deb.controlfile import ControlFile
from deb.controlfileparser import ControlFileParser
from deb.version import Version
from momlib import md5sum
from util import tree


logger = logging.getLogger('debcontrolmerger')


def field_name(package, field):
    if package:
        return "%s/%s" % (package, field)
    else:
        return field


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
            (self.merge_depends, (None, 'Build-Depends')),
            (self.merge_depends, (None, 'Build-Depends-Indep')),
            (self.merge_depends, (None, 'Build-Conflicts')),
            (self.merge_package_depends, ('Depends',)),
            (self.merge_package_depends, ('Replaces',)),
            (self.merge_package_depends, ('Provides',)),
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

    def __merge_modified_version_constraint(self, package, field, entry,
                                            base_dep, left_dep, right_dep):
        if right_dep is None:
            logging.debug('Drop modified %s %s', field_name(package, field),
                          entry)
            self.left_control.patch_at_offset(left_dep.position, base_dep)
            self.left_control.write()

            self.record_note('Dropped modified %s %s because this '
                             'dependency disappeared from the upstream '
                             'version' % (field_name(package, field), entry),
                             True)
            return

        base_vc = base_dep.version_constraint
        left_vc = left_dep.version_constraint
        right_vc = right_dep.version_constraint

        # If the left version increases the minimum version required,
        # but the right version increases it even more, then drop our
        # left-side change.
        if right_vc is not None and right_vc.startswith(">") \
                and base_vc is not None and base_vc.startswith(">") \
                and left_vc is not None and left_vc.startswith(">"):
            base_min = Version(base_vc.split()[1])
            left_min = Version(left_vc.split()[1])
            right_min = Version(right_vc.split()[1])
            if left_min > base_min and right_min > left_min:
                # Restore original version constraint on the left
                self.left_control.patch_at_offset(left_vc.position, base_vc)
                self.left_control.write()

                self.record_note('Dropped modified %s %s %s version '
                                 'constraint because upstream increased it '
                                 'further' % (field_name(package, field),
                                              left_vc, entry),
                                 True)
                return

        if right_vc is not None:
            logging.debug('Apply %s %s modified version constraint',
                          field_name(package, field), entry)

            self.right_control.patch_at_offset(right_vc.position, left_vc)
            self.right_control.write()

            # Restore original version constraint on the left to ease the merge
            self.left_control.patch_at_offset(left_vc.position, base_vc)
            self.left_control.write()

            self.record_note('Reapplied modified %s %s %s version '
                             'constraint'
                             % (field_name(package, field),
                                left_vc, entry))

    def __merge_added_dep(self, package, field, entry, left_dep, right_dep):
        if right_dep is None:
            # If a dependency was added on the left, but is not present on
            # the right, add it there.
            self.right_control.add_depends_entry(package, field,
                                                 unicode(left_dep))
            self.right_control.write()
            self.record_note('Carried forward change to add %s %s'
                             % (field_name(package, field), entry))
        else:
            # If a dependency was added on the left and is now present
            # on the right, we can just drop the change on the left.
            self.record_note('Dropped %s %s addition since it is now present '
                             'on the right'
                             % (field_name(package, field), entry), True)

        # Drop our change on the left to ease the merge
        self.left_control.remove_depends_entry(package, field, entry)
        self.left_control.write()

    # Merge Dependencies fields
    def merge_depends(self, package, field):
        base_text = self.base_control.get_paragraph(package).get(field)
        left_text = self.left_control.get_paragraph(package).get(field)

        if base_text == left_text:
            return

        base_deps = self.base_control.parse_depends(package, field)
        left_deps = self.left_control.parse_depends(package, field)
        right_deps = self.right_control.parse_depends(package, field)

        logger.debug('Detected %s difference, trying to merge',
                     field_name(package, field))

        # For each build dependency on the left, check if it has a modified
        # version constraint compared to the base.
        # If so, and if the right version doesn't have that build dependency
        # at all, drop our local change by restoring the original version
        # constraint.
        for pkg in left_deps.keys():
            if pkg not in base_deps:
                continue

            base_bdep = base_deps[pkg]
            left_bdep = left_deps[pkg]
            if left_bdep.version_constraint == base_bdep.version_constraint:
                continue

            right_bdep = right_deps.get(pkg)
            self.__merge_modified_version_constraint(package, field, pkg,
                                                     base_bdep, left_bdep,
                                                     right_bdep)

            # Reparse after changes
            left_deps = self.left_control.parse_depends(package, field)
            right_deps = self.right_control.parse_depends(package, field)

        # If a package was removed in the left version and also on the right,
        # remove it from the base version in order to ease up the merge.
        for pkg in base_deps.keys():
            if pkg in left_deps or pkg in right_deps:
                continue

            logging.debug('Dropping %s %s from base as it was dropped from '
                          'left and right', field_name(package, field), pkg)
            self.base_control.remove_depends_entry(package, field, pkg)
            self.base_control.write()

            # Reparse after changes
            base_deps = self.base_control.parse_depends(package, field)

            self.record_note('Dropped removed %s %s because this '
                             'dependency also disappeared from the upstream '
                             'version' % (field_name(package, field), pkg),
                             True)

        # If a package was removed in the left version and can still be
        # removed from the right, remove it from base and right to ease up
        # the merge. (The more logical alternative of reintroducing the
        # dep on the left side is more complicated than removing...)
        for pkg in base_deps.keys():
            if pkg in left_deps or pkg not in right_deps:
                continue

            logging.debug('Dropping %s %s from base and right as it was '
                          'dropped from left', field_name(package, field), pkg)
            self.base_control.remove_depends_entry(package, field, pkg)
            self.base_control.write()

            self.right_control.remove_depends_entry(package, field, pkg)
            self.right_control.write()

            # Reparse after changes
            base_deps = self.base_control.parse_depends(package, field)
            right_deps = self.right_control.parse_depends(package, field)

            self.record_note('Carried forward removal of %s %s'
                             % (field_name(package, field), pkg))

        # Handle dependencies added on the left
        for pkg in left_deps.keys():
            if pkg in base_deps:
                continue

            self.__merge_added_dep(package, field, pkg, left_deps[pkg],
                                   right_deps.get(pkg))

            # Reparse after changes
            left_deps = self.left_control.parse_depends(package, field)
            right_deps = self.right_control.parse_depends(package, field)

        # Handle dependencies where an arch list was added on the left,
        # where the base did not have any list.
        for pkg in base_deps.keys():
            if pkg not in left_deps or pkg not in right_deps:
                continue

            left_bdep = left_deps[pkg]
            base_bdep = base_deps[pkg]

            if base_bdep.arch_list is not None or left_bdep.arch_list is None:
                continue

            right_bdep = right_deps[pkg]

            logger.debug('Carrying over %s %s added arch list',
                         field_name(package, field), pkg)

            new_val = unicode(right_bdep) + " [" + left_bdep.arch_list + "]"
            self.right_control.patch_at_offset(right_bdep.position, new_val)
            self.right_control.write()

            # Drop the original change on the left side by restoring the
            # dependency from the base version, in hope of aiding the merge.
            self.left_control.patch_at_offset(left_bdep.position, base_bdep)
            self.left_control.write()

            self.record_note('Carried forward change to add arch list '
                             '[%s] to %s %s'
                             % (left_bdep.arch_list, field, pkg))

        # If there's no remaining difference in the actual build-depends list
        # and it's just changes in spaces/commas/etc then just drop our
        # changes on the left.
        base_text = self.base_control.get_paragraph(package).get(field)
        left_text = self.left_control.get_paragraph(package).get(field)
        if base_text != left_text \
                and sorted(left_deps.items()) == sorted(base_deps.items()):
            self.__restore_original_value(package, field)
            self.record_note('Tweaked %s syntax to ease the merge'
                             % field_name(package, field))

    def merge_package_depends(self, field):
        for pkg in self.base_control.get_package_names():
            if self.left_control.get_paragraph(pkg) \
                    and self.right_control.get_paragraph(pkg):
                self.merge_depends(pkg, field)
