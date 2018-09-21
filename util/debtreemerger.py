import logging
import os
import shutil
from stat import *
import subprocess
from subprocess import Popen
from tempfile import mkdtemp, NamedTemporaryFile

from deb.controlfile import ControlFile
from deb.controlfilepatcher import ControlFilePatcher
from momlib import *
from util import tree

logger = logging.getLogger('debtreemerger')


def same_file(left_stat, left_dir, right_stat, right_dir, filename):
    """Are two filesystem objects the same?"""
    if S_IFMT(left_stat.st_mode) != S_IFMT(right_stat.st_mode):
        # Different fundamental types
        return False
    elif S_ISREG(left_stat.st_mode):
        # Files with the same size and MD5sum are the same
        if left_stat.st_size != right_stat.st_size:
            return False
        elif md5sum("%s/%s" % (left_dir, filename)) \
                != md5sum("%s/%s" % (right_dir, filename)):
            return False
        else:
            return True
    elif S_ISDIR(left_stat.st_mode) or S_ISFIFO(left_stat.st_mode) \
            or S_ISSOCK(left_stat.st_mode):
        # Directories, fifos and sockets are always the same
        return True
    elif S_ISCHR(left_stat.st_mode) or S_ISBLK(left_stat.st_mode):
        # Char/block devices are the same if they have the same rdev
        if left_stat.st_rdev != right_stat.st_rdev:
            return False
        else:
            return True
    elif S_ISLNK(left_stat.st_mode):
        # Symbolic links are the same if they have the same target
        if os.readlink("%s/%s" % (left_dir, filename)) \
               != os.readlink("%s/%s" % (right_dir, filename)):
            return False
        else:
            return True
    else:
        return True


class DebTreeMerger(object):
    # Describe the entries in changes_made
    FILE_ADDED = 1
    FILE_REMOVED = 2
    FILE_MODIFIED = 3

    # Describe the entries in pending_changes
    # Copy modified file from left version
    PENDING_SYNC = 1
    # Copy added file from left version
    PENDING_ADD = 2
    # Remove from right version
    PENDING_REMOVE = 3
    # 3-way merge needed
    PENDING_MERGE = 4

    def __init__(self, left_dir, left_name, left_format, left_distro,
                 right_dir, right_name, right_format, right_distro,
                 base_dir, merged_dir):
        self.left_dir = left_dir
        self.left_name = left_name
        self.left_format = left_format
        self.left_distro = left_distro
        self.right_dir = right_dir
        self.right_name = right_name
        self.right_format = right_format
        self.right_distro = right_distro
        self.base_dir = base_dir
        self.merged_dir = merged_dir

        # Specific merge-related information to flag to the maintainer
        self.notes = []

        # Changes pending as part of the merge
        self.pending_changes = {}

        # Changes made relative to the right version
        self.changes_made = {}

        # Files that generated conflicts when merging
        self.conflicts = set()

    @property
    def total_changes_made(self):
        """Total number of modifications made relative to the right version"""
        return len(self.changes_made)

    @property
    def modified_files(self):
        return [k for k, v in self.changes_made.iteritems()
                if v == self.FILE_MODIFIED]

    # Record a change made relative to the right version
    def record_change(self, filename, change_type):
        if filename in self.changes_made:
            assert self.changes_made[filename] == change_type

        self.changes_made[filename] = change_type

    # Record a pending change to make in the merge directory
    def record_pending_change(self, filename, pending_change_type):
        assert filename not in self.pending_changes
        self.pending_changes[filename] = pending_change_type

    # Apply a specific pending change to a file.
    # Return the type of change made, or None if it conflicted
    def apply_pending_change(self, filename, change_type):
        if change_type == self.PENDING_SYNC:
            # sync from left (file or non file)
            tree.copyfile("%s/%s" % (self.left_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))
            return self.FILE_MODIFIED

        elif change_type == self.PENDING_ADD:
            # add from left
            tree.copyfile("%s/%s" % (self.left_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))
            return self.FILE_ADDED

        elif change_type == self.PENDING_REMOVE:
            os.unlink('%s/%s' % (self.merged_dir, filename))
            return self.FILE_REMOVED

        elif change_type == self.PENDING_MERGE:
            # Handle pending merges
            try:
                base_stat = os.lstat("%s/%s" % (self.base_dir, filename))
            except OSError:
                base_stat = None

            try:
                left_stat = os.lstat("%s/%s" % (self.left_dir, filename))
            except OSError:
                left_stat = None

            try:
                right_stat = os.lstat("%s/%s" % (self.right_dir, filename))
            except OSError:
                right_stat = None

            if self.merge_file_contents(left_stat, right_stat, base_stat,
                                        filename):
                # Merge file permissions
                self.merge_attr(filename)
                return self.FILE_MODIFIED
            else:
                return None

        else:
            raise Exception("Unknown pending change type %d" % change_type)

    # Apply the pending change to the given file
    # Remove the entry from the pending changes list
    # Return the type of change made, or None if it conflicted
    def apply_pending_change_to_file(self, filename):
        r = self.apply_pending_change(filename, self.pending_changes[filename])
        if r is not None:
            self.record_change(filename, r)
        else:
            self.conflicts.add(filename)

        del self.pending_changes[filename]
        return r

    # Apply all pending changes
    def apply_pending_changes(self):
        for filename in self.pending_changes.keys():
            self.apply_pending_change_to_file(filename)

    def run(self):
        """Do the heavy lifting of comparing and merging."""
        logger.debug("Producing merge in %s", self.merged_dir)

        both_formats_quilt = \
            self.left_format == self.right_format == "3.0 (quilt)"
        if both_formats_quilt:
            logger.debug("Only merging debian directory since both "
                         "formats 3.0 (quilt)")

        # Look for files in the base and merge them if they're in both new
        # files (removed files get removed)
        for filename in tree.walk(self.base_dir):
            # If both packages are 3.0 (quilt), ignore everything except
            # the debian directory
            if both_formats_quilt and not tree.under("debian", filename):
                continue

            if tree.under(".pc", filename):
                # Not interested in merging quilt metadata
                continue

            base_stat = os.lstat("%s/%s" % (self.base_dir, filename))
            try:
                left_stat = os.lstat("%s/%s" % (self.left_dir, filename))
            except OSError:
                left_stat = None

            try:
                right_stat = os.lstat("%s/%s" % (self.right_dir, filename))
            except OSError:
                right_stat = None

            if left_stat is None and right_stat is None:
                # Removed on both sides
                pass

            elif left_stat is None:
                logger.debug("removed from %s: %s", self.left_distro, filename)
                if not same_file(base_stat, self.base_dir, right_stat,
                                 self.right_dir, filename):
                    # Changed on RHS
                    self.conflicts.add(filename)
                else:
                    # File was remvoed on left. Put it in place in the merged
                    # dir but record it as a pending deletion.
                    tree.copyfile("%s/%s" % (self.right_dir, filename),
                                  "%s/%s" % (self.merged_dir, filename))
                    self.record_pending_change(filename, self.PENDING_REMOVE)

            elif right_stat is None:
                # Removed on RHS only
                logger.debug("removed from %s: %s", self.right_distro,
                             filename)
                if not same_file(base_stat, self.base_dir,
                                 left_stat, self.left_dir, filename):
                    # Changed on LHS
                    self.conflicts.add(filename)

            elif S_ISREG(left_stat.st_mode) and S_ISREG(right_stat.st_mode):
                # Common case: left and right are both files
                self.handle_file(left_stat, right_stat, base_stat, filename)

            elif same_file(left_stat, self.left_dir,
                           right_stat, self.right_dir, filename):
                # left and right are the same, doesn't matter which we keep
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))

            elif same_file(base_stat, self.base_dir,
                           left_stat, self.left_dir, filename):
                # right has changed in some way, keep that one
                logger.debug("preserving non-file change in %s: %s",
                             self.right_distro, filename)
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))

            elif same_file(base_stat, self.base_dir,
                           right_stat, self.right_dir, filename):
                # left has changed in some way, keep that one
                logger.debug("preserving non-file change in %s: %s",
                             self.left_distro, filename)
                self.record_pending_change(filename, self.PENDING_SYNC)
            else:
                # all three differ, mark a conflict
                self.conflicts.add(filename)

        # Look for files in the left hand side that aren't in the base,
        # conflict if new on both sides or copy into the tree
        for filename in tree.walk(self.left_dir):
            # If both packages are 3.0 (quilt), ignore everything except the
            # debian directory
            if both_formats_quilt and not tree.under("debian", filename):
                continue

            if tree.under(".pc", filename):
                # Not interested in merging quilt metadata
                continue

            if tree.exists("%s/%s" % (self.base_dir, filename)):
                continue

            if not tree.exists("%s/%s" % (self.right_dir, filename)):
                logger.debug("new in %s: %s", self.left_distro, filename)
                self.record_pending_change(filename, self.PENDING_ADD)
                continue

            left_stat = os.lstat("%s/%s" % (self.left_dir, filename))
            right_stat = os.lstat("%s/%s" % (self.right_dir, filename))

            if S_ISREG(left_stat.st_mode) and S_ISREG(right_stat.st_mode):
                # Common case: left and right are both files
                self.handle_file(left_stat, right_stat, None, filename)

            elif same_file(left_stat, self.left_dir,
                           right_stat, self.right_dir, filename):
                # left and right are the same, doesn't matter which we keep
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))

            else:
                # they differ, mark a conflict
                self.conflicts.add(filename)

        # Copy new files on the right hand side only into the tree
        for filename in tree.walk(self.right_dir):
            if tree.under(".pc", filename):
                # Not interested in merging quilt metadata
                continue

            if both_formats_quilt and not tree.under("debian", filename):
                # Always copy right version for quilt non-debian files
                if not tree.exists("%s/%s" % (self.left_dir, filename)):
                    logger.debug("new in %s: %s", self.right_distro, filename)
            else:
                if tree.exists("%s/%s" % (self.base_dir, filename)):
                    continue

                if tree.exists("%s/%s" % (self.left_dir, filename)):
                    continue

                logger.debug("new in %s: %s", self.right_distro, filename)

            tree.copyfile("%s/%s" % (self.right_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))

        # At this point, merged_dir resembles the right version and we have
        # recorded the changes that we need to make.
        # Before we proceed with (attempting) to make those changes through
        # simple means, see which changes we can make through context-specific
        # methods, which are likely to avoid conflicts.

        # Handle po files separately as they need special merging
        # Do POT files because they can be useful when later merging PO files
        self.handle_pot_files()
        self.handle_po_files()

        # Intelligently handle added quilt patches
        self.handle_quilt_patches()

        # Intelligently handle control file
        self.handle_control_file()

        # Now apply the remaining changes through simple means
        self.apply_pending_changes()

        for conflict in self.conflicts:
            self.conflict_file(conflict)

    # Handle the merge of the quilt series file
    # Return True (and delete pending_changes, and do record_change) if
    # successul
    # Return False if not (leaving it on pending_changes)
    def merge_quilt_series(self):
        series_file = 'debian/patches/series'

        # If it's not a merge then just resolve it normally
        if self.pending_changes[series_file] != self.PENDING_MERGE:
            return False

        try:
            base_stat = os.stat("%s/%s" % (self.base_dir, series_file))
        except OSError:
            base_stat = None

        # If we have a base version, see if diff3 can figure it out cleanly
        if base_stat is not None and S_ISREG(base_stat.st_mode) \
                and self.diff3_merge(series_file):
            del self.pending_changes[series_file]
            self.record_change(series_file, self.FILE_MODIFIED)
            return True

        # No easy merge options, so try to merge intelligently.
        # Handle the case where the downstream changes are just appending
        # patches to the end of the list - in which case we can just append
        # the same patches to the end of the new right version series file.

        # Base series file might not exist if the conflict is due to different
        # series files being added in left and right versions
        try:
            base = open(os.path.join(self.base_dir, series_file), 'r').read()
        except IOError as e:
            if e.errno == errno.ENOENT:
                base = ''
            else:
                raise

        left = open(os.path.join(self.left_dir, series_file), 'r').read()

        # Only proceed if our changes were additions at the end of the file
        if not left.startswith(base):
            return False

        logging.debug('Merging quilt series by readding our end-of-file '
                      'additions')
        added_data = left[len(base):]
        tree.ensure(os.path.join(self.merged_dir, series_file))
        shutil.copy2(os.path.join(self.right_dir, series_file),
                     os.path.join(self.merged_dir, series_file))
        with open(os.path.join(self.merged_dir, series_file), 'a') as fd:
            fd.write(added_data)

        del self.pending_changes[series_file]
        self.record_change(series_file, self.FILE_MODIFIED)
        self.notes.append('Downstream additions to quilt series file were '
                          're-appended on top of new upstream version')
        return True

    def handle_quilt_patches(self):
        if 'debian/patches/series' not in self.pending_changes:
            return

        merged = self.merge_quilt_series()
        if not merged:
            merged = \
                self.apply_pending_change_to_file('debian/patches/series') \
                is not None

        if not merged:
            logging.debug('Skip quilt patches handling as series file '
                          'conflicted')
            return

        # Experiment with patch reverts under a temporary copy
        tmpdir = mkdtemp(prefix='mom.quiltrevert.')
        try:
            os.rmdir(tmpdir)
            shutil.copytree(self.merged_dir, tmpdir, symlinks=True)
            self.__revert_quilt_patches(tmpdir)
        finally:
            shutil.rmtree(tmpdir)

        # Experiment with patch refreshes under a temporary copy
        tmpdir = mkdtemp(prefix='mom.quiltrefresh.')
        try:
            os.rmdir(tmpdir)
            shutil.copytree(self.merged_dir, tmpdir, symlinks=True)
            self.__refresh_quilt_patches(tmpdir)
        finally:
            shutil.rmtree(tmpdir)

    def __revert_quilt_patches(self, tmpdir):
        # get list of patches applied in base version
        proc = subprocess.Popen(['quilt', 'series'], stdout=subprocess.PIPE,
                                env={'QUILT_PATCHES': 'debian/patches'},
                                cwd=self.base_dir)
        base_series, stderr = proc.communicate()
        if proc.returncode != 0:
            logging.debug('quilt series failed in base version')
            return

        # get list of patches applied in our version
        proc = subprocess.Popen(['quilt', 'series'], stdout=subprocess.PIPE,
                                env={'QUILT_PATCHES': 'debian/patches'},
                                cwd=self.left_dir)
        our_series, stderr = proc.communicate()
        if proc.returncode != 0:
            logging.debug('quilt series failed in left version')
            return

        # find list of patches that we add - without losing order
        base_series = base_series.split("\n")
        our_series = our_series.split("\n")
        our_added_patches = []
        for patch in our_series:
            if patch not in base_series:
                our_added_patches.append(os.path.basename(patch))

        # revert them one by one
        patches_to_drop = []
        for patch in reversed(our_added_patches):
            logging.debug('Trying to revert our patch %s', patch)
            args = ['patch', '--dry-run', '-p1', '--reverse', '--force',
                    '--quiet', '-i',
                    os.path.join(self.left_dir, 'debian', 'patches', patch)]
            rc = subprocess.call(args, cwd=tmpdir)
            if rc != 0:
                continue

            # Patch can be reverted. Note this and do the revert, in case
            # the following patches depend on this one being reverted.
            del args[1]
            subprocess.call(args, cwd=tmpdir)
            patches_to_drop.append(patch)

        if not patches_to_drop:
            return

        # Remove revertable patches from series file
        series_file = os.path.join(self.merged_dir, 'debian', 'patches',
                                   'series')
        written = False
        with open(series_file) as series, NamedTemporaryFile() as new_series:
            for line in series.readlines():
                if line.strip() in patches_to_drop:
                    continue
                new_series.write(line)
                written = True
            new_series.flush()
            shutil.copyfile(new_series.name, series_file)

        for patch in patches_to_drop:
            logging.debug('Dropping revertable patch %s', patch)
            del self.pending_changes['debian/patches/' + patch]
            self.notes.append('Dropped patch %s because it can be reverted '
                              'cleanly' % patch)

        if not written:
            logging.debug('No quilt patches remaining, removing directory')
            self.notes.append('debian/patches was entirely removed as there '
                              'were no patches remaining.')
            os.unlink(series_file)
            os.rmdir(os.path.join(self.merged_dir, 'debian', 'patches'))
            del self.changes_made['debian/patches/series']

    def __refresh_quilt_patches(self, tmpdir):
        # Put our downstream-added patches in place. Must be done
        # before we 'quilt push' the preceding patch to avoid quilt being
        # unhappy.
        for filename, change_type in self.pending_changes.iteritems():
            if filename.startswith('debian/patches/') \
                    and filename.endswith('.patch') \
                    and change_type == self.PENDING_ADD:
                shutil.copy2(os.path.join(self.left_dir, filename),
                             os.path.join(tmpdir, filename))

        quiltexec = {'env': {'QUILT_PATCHES': 'debian/patches'}, 'cwd': tmpdir}

        # Go over every quilt patch in the series, and attempt to fix any of
        # our patches that are broken.
        while True:
            proc = subprocess.Popen(['quilt', 'next'], stdout=subprocess.PIPE,
                                    **quiltexec)
            patch, stderr = proc.communicate()
            if proc.returncode != 0:
                logging.debug('quilt next failed, assuming end of series')
                return

            patch = patch.strip()
            logging.debug('Next patch is %s', patch)

            if patch not in self.pending_changes \
                    or self.pending_changes[patch] != self.PENDING_ADD:
                # Only work on patches that we added in our version
                logging.debug('%s is not our patch, apply and skip', patch)
                rc = subprocess.call(['quilt', 'push'], **quiltexec)
                if rc != 0:
                    logging.warning('Failed to apply base patch %s', patch)
                    return
                continue

            # Try to apply with no fuzz, like Debian does
            rc = subprocess.call(['quilt', 'push', '--fuzz=0'], **quiltexec)
            if rc == 0:
                # Patch applied without fuzz, nothing to do
                logging.debug('%s applied without fuzz, nothing to do', patch)
                continue

            # Try applying with fuzz
            logging.debug('%s failed to apply, trying with fuzz', patch)
            rc = subprocess.call(['quilt', 'push'], **quiltexec)
            if rc == 0:
                # Patch applies with fuzz, refresh it
                logging.debug('%s now applied, refreshing', patch)
                self.notes.append('%s was refreshed to eliminate fuzz' % patch)
                subprocess.check_call(['quilt', 'refresh'], **quiltexec)
                shutil.copy2(os.path.join(tmpdir, patch),
                             os.path.join(self.merged_dir, patch))
                del self.pending_changes[patch]
                self.record_change(patch, self.FILE_ADDED)
            else:
                logging.debug('%s still failed to apply', patch)
                self.notes.append('Our patch %s fails to apply to the new '
                                  'version' % patch)
                return

    def handle_control_file(self):
        control_file = 'debian/control'
        if control_file not in self.pending_changes or \
                self.pending_changes[control_file] != self.PENDING_MERGE:
            return

        try:
            base_stat = os.stat("%s/%s" % (self.base_dir, control_file))
        except OSError:
            return

        if not S_ISREG(base_stat.st_mode):
            return

        # If we have a base version, see if diff3 can figure it out cleanly
        if self.diff3_merge(control_file):
            del self.pending_changes[control_file]
            self.record_change(control_file, self.FILE_MODIFIED)
            logger.debug('Merged debian/control file via diff3')
            return

        our_control_path = os.path.join(self.left_dir, control_file)
        base_control = ControlFile(os.path.join(self.base_dir, control_file),
                                   multi_para=True)
        our_control = ControlFile(our_control_path, multi_para=True)

        # See if we've modified Uploaders in our version
        base_uploaders = base_control.paras[0].get('Uploaders', None)
        our_uploaders = our_control.paras[0].get('Uploaders', None)
        if base_uploaders == our_uploaders:
            return

        # If so, rewrite our own control file with the original Uploaders
        logging.debug('Restoring Uploaders to base value to see if it helps '
                      'with conflict resolution')
        control_patcher = ControlFilePatcher(filename=our_control_path)
        control_patcher.patch('Uploaders', base_uploaders)

        # Try diff3 again with the modified left version.
        with open(our_control_path, "w") as new_control:
            new_control.write(control_patcher.get_text())
            new_control.flush()

        if self.diff3_merge(control_file):
            logging.debug('control file merge now succeeded')
            del self.pending_changes[control_file]
            self.record_change(control_file, self.FILE_MODIFIED)
            self.notes.append('Dropped uninteresting Uploaders change in '
                              'downstream debian/control file')
        else:
            logging.debug('control file still could not be merged')

    # Handle po files separately as they need special merging
    def handle_pot_files(self):
        for filename, change_type in self.pending_changes.items():
            if not filename.endswith('.pot'):
                continue
            if change_type != self.PENDING_MERGE:
                continue

            if self.merge_pot(filename):
                self.merge_attr(filename)
                self.record_change(filename, self.FILE_MODIFIED)
                del self.pending_changes[filename]
            else:
                self.conflicts.add(filename)

    # Handle po files separately as they need special merging
    def handle_po_files(self):
        for filename, change_type in self.pending_changes.items():
            if not filename.endswith('.po'):
                continue
            if change_type != self.PENDING_MERGE:
                continue

            if self.merge_po(filename):
                self.merge_attr(filename)
                self.record_change(filename, self.FILE_MODIFIED)
                del self.pending_changes[filename]
            else:
                self.conflicts.add(filename)

    def merge_pot(self, filename):
        """Update a .po file using msgcat."""
        merged_pot = "%s/%s" % (self.merged_dir, filename)
        left_pot = "%s/%s" % (self.left_dir, filename)
        right_pot = "%s/%s" % (self.right_dir, filename)

        logger.debug("Merging POT file %s", filename)
        try:
                tree.ensure(merged_pot)
                shell.run(("msgcat", "--force-po", "--use-first", "-o",
                           merged_pot, right_pot, left_pot))
        except (ValueError, OSError):
                logger.error("POT file merge failed: %s", filename)
                return False

        return True

    def merge_po(self, filename):
        """Update a .po file using msgcat or msgmerge."""
        merged_po = "%s/%s" % (self.merged_dir, filename)
        closest_pot = self.find_closest_pot(merged_po)
        if closest_pot is None:
            return self.merge_pot(filename)

        left_po = "%s/%s" % (self.left_dir, filename)
        right_po = "%s/%s" % (self.right_dir, filename)

        logger.debug("Merging PO file %s", filename)
        try:
            tree.ensure(merged_po)
            shell.run(("msgmerge", "--force-po", "-o", merged_po,
                       "-C", left_po, right_po, closest_pot))
        except (ValueError, OSError):
            logger.error("PO file merge failed: %s", filename)
            return False

        return True

    def find_closest_pot(self, po_file):
        """Find the closest .pot file to the po file given."""
        dirname = os.path.dirname(po_file)
        for entry in os.listdir(dirname):
            if entry.endswith(".pot"):
                return os.path.join(dirname, entry)
        else:
            return None

    def handle_file(self, left_stat, right_stat, base_stat, filename):
        """Handle the common case of a file in both left and right."""
        do_attrs = True

        if base_stat and \
                same_file(base_stat, self.base_dir,
                          left_stat, self.left_dir, filename):
            # same file contents in base and left, meaning that the left
            # side was unmodified, so take the right side as-is
            logger.debug("%s was unmodified on the left", filename)
            tree.copyfile("%s/%s" % (self.right_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))
            self.merge_attr(filename)
        elif same_file(left_stat, self.left_dir,
                       right_stat, self.right_dir, filename):
            # same file contents in left and right
            logger.debug("%s and %s both turned into same file: %s",
                         self.left_distro, self.right_distro, filename)
            tree.copyfile("%s/%s" % (self.left_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))
            self.merge_attr(filename)
        else:
            self.record_pending_change(filename, self.PENDING_MERGE)

    # Returns True if the merge succeeded, or False if the merge generated
    # conflicts.
    def merge_file_contents(self, left_stat, right_stat, base_stat, filename):
        if filename == "debian/changelog":
            # two-way merge of changelogs
            try:
                self.merge_changelog(filename)
                return True
            except Exception:
                return False
        elif base_stat is not None and S_ISREG(base_stat.st_mode):
            # was file in base: diff3 possible
            if self.diff3_merge(filename):
                return True
            if self.sbtm_merge(filename):
                return True
            if self.sbtm_merge(filename, fast=True):
                return True
        # general file conflict
        return False

    def merge_changelog(self, filename):
        """Merge a changelog file."""
        logger.debug("Knitting %s", filename)

        left_cl = read_changelog("%s/%s" % (self.left_dir, filename))
        right_cl = read_changelog("%s/%s" % (self.right_dir, filename))
        tree.ensure(filename)

        with open("%s/%s" % (self.merged_dir, filename), "w") as output:
            for right_ver, right_text in right_cl:
                while len(left_cl) and left_cl[0][0] > right_ver:
                    (left_ver, left_text) = left_cl.pop(0)
                    print >>output, left_text

                while len(left_cl) and left_cl[0][0] == right_ver:
                    (left_ver, left_text) = left_cl.pop(0)

                print >>output, right_text

            for left_ver, left_text in left_cl:
                print >>output, left_text

        return False

    def diff3_merge(self, filename):
        """Merge a file using diff3."""
        dest = "%s/%s" % (self.merged_dir, filename)
        tree.ensure(dest)

        with open(dest, "w") as output:
            status = shell.run(("diff3", "-E", "-m",
                                "-L", self.left_name,
                                "%s/%s" % (self.left_dir, filename),
                                "-L", "BASE",
                                "%s/%s" % (self.base_dir, filename),
                                "-L", self.right_name,
                                "%s/%s" % (self.right_dir, filename)),
                               stdout=output, okstatus=(0, 1, 2))

        if status == 0:
            return True

        if not tree.exists(dest) or os.stat(dest).st_size == 0:
            # Probably binary
            if same_file(os.stat("%s/%s" % (self.left_dir, filename)),
                         self.left_dir,
                         os.stat("%s/%s" % (self.right_dir, filename)),
                         self.right_dir,
                         filename):
                logger.debug("binary files are the same: %s", filename)
                tree.copyfile("%s/%s" % (self.left_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
            elif same_file(os.stat("%s/%s" % (self.base_dir, filename)),
                           self.base_dir,
                           os.stat("%s/%s" % (self.left_dir, filename)),
                           self.left_dir,
                           filename):
                logger.debug("preserving binary change in %s: %s",
                             self.right_distro, filename)
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
            elif same_file(os.stat("%s/%s" % (self.base_dir, filename)),
                           self.base_dir,
                           os.stat("%s/%s" % (self.right_dir, filename)),
                           self.right_dir,
                           filename):
                logger.debug("preserving binary change in %s: %s",
                             self.left_distro, filename)
                tree.copyfile("%s/%s" % (self.left_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
            else:
                logger.debug("binary file conflict: %s", filename)
                return False
        else:
            logger.debug("Conflict in %s", filename)
            return False

    def sbtm_merge(self, filename, fast=False):
        """Merge a file using State-Based Text Merge tool.
        This is experimental and often fails, but has been shown to
        work correctly in some cases.

        The alternate "--fast" algorithm is less likely to exhaust
        recursion limits, but also less likely to produce accurate
        results."""
        dest = "%s/%s" % (self.merged_dir, filename)
        tree.ensure(dest)

        # We run this python app as a separate process as it does a lot of
        # recursion and can cause high memory usage, stack overflow, etc.
        args = [os.path.join(os.path.abspath(os.path.dirname(__file__)),
                             'sbtm.py')]
        if fast:
            args.append('--fast')
        args.append("%s/%s" % (self.base_dir, filename))
        args.append("%s/%s" % (self.left_dir, filename))
        args.append("%s/%s" % (self.right_dir, filename))

        process = Popen(args,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            return False

        with open(dest, "w") as output:
            output.write(stdout)

        note = '%s was merged with an experimental '\
               'State-Based Text Merge tool' % filename
        if fast:
            note += ' using the fast diff algorithm (particularly prone to ' \
                    'inaccuracies)'
        self.notes.append(note)

        return True

    def merge_attr(self, filename):
        """Set initial and merge changed attributes."""
        if os.path.isfile("%s/%s" % (self.base_dir, filename)) \
                and not os.path.islink("%s/%s" % (self.base_dir, filename)):
            self.set_attr(self.base_dir, self.merged_dir, filename)
            self.apply_attr(self.base_dir, self.left_dir, self.merged_dir,
                            filename)
            self.apply_attr(self.base_dir, self.right_dir, self.merged_dir,
                            filename)
        else:
            self.set_attr(self.right_dir, self.merged_dir, filename)
            self.apply_attr(self.right_dir, self.left_dir, self.merged_dir,
                            filename)

    def set_attr(self, src_dir, dest_dir, filename):
        """Set the initial attributes."""
        mode = os.stat("%s/%s" % (src_dir, filename)).st_mode & 0777
        os.chmod("%s/%s" % (dest_dir, filename), mode)

    def apply_attr(self, base_dir, src_dir, dest_dir, filename):
        """Apply attribute changes from one side to a file."""
        src_stat = os.stat("%s/%s" % (src_dir, filename))
        base_stat = os.stat("%s/%s" % (base_dir, filename))
        changed = False

        for shift in range(0, 9):
            bit = 1 << shift

            # Permission bit added
            if not base_stat.st_mode & bit and src_stat.st_mode & bit:
                self.change_attr(dest_dir, filename, bit, shift, True)
                changed = True

            # Permission bit removed
            if base_stat.st_mode & bit and not src_stat.st_mode & bit:
                self.change_attr(dest_dir, filename, bit, shift, False)
                changed = True

        if changed:
            self.record_change(filename, self.FILE_MODIFIED)

    def change_attr(self, dest_dir, filename, bit, shift, add):
        """Apply a single attribute change."""
        logger.debug("Setting %s %s", filename,
                     ["u+r", "u+w", "u+x", "g+r", "g+w", "g+x",
                      "o+r", "o+w", "o+x"][shift])

        dest = "%s/%s" % (dest_dir, filename)
        attr = os.stat(dest).st_mode & 0777
        if add:
            attr |= bit
        else:
            attr &= ~bit

        os.chmod(dest, attr)

    def conflict_file(self, filename):
        """Copy both files as conflicts of each other."""
        left_src = "%s/%s" % (self.left_dir, filename)
        right_src = "%s/%s" % (self.right_dir, filename)
        dest = "%s/%s" % (self.merged_dir, filename)

        logger.debug("Conflicted: %s", filename)
        tree.remove(dest)

        # We need to take care here .. if one of the items involved in a
        # conflict is a directory then it might have children and we don't want
        # to throw an error later.
        #
        # We get round this by making the directory a symlink to the conflicted
        # one.
        #
        # Fortunately this is so rare it may never happen!

        if tree.exists(left_src):
            tree.copyfile(left_src, "%s.%s" % (dest, self.left_distro.upper()))
        if os.path.isdir(left_src):
            os.symlink("%s.%s" % (os.path.basename(dest),
                                  self.left_distro.upper()),
                       dest)

        if tree.exists(right_src):
            tree.copyfile(right_src,
                          "%s.%s" % (dest, self.right_distro.upper()))
        if os.path.isdir(right_src):
            os.symlink("%s.%s" % (os.path.basename(dest),
                                  self.right_distro.upper()),
                       dest)
