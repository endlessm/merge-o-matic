import errno
import logging
import os
import shutil
from stat import *
import subprocess
from subprocess import Popen, CalledProcessError
from tempfile import mkdtemp, NamedTemporaryFile

from deb.controlfile import ControlFile
from deb.controlfileparser import ControlFileParser
from momlib import *
from util import tree
from util.debcontrolmerger import DebControlMerger

logger = logging.getLogger('debtreemerger')

class FileInfo(object):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return str(self.path)

    def __unicode__(self):
        return unicode(self.path)

    @property
    def exists(self):
        return os.path.exists(self.path) or os.path.islink(self.path)

    # stat the file and cache the results.
    # Future calls will use the cached data.
    @property
    def stat(self):
        if hasattr(self, 'stat_data'):
            return self.stat_data
        try:
            self.stat_data = os.lstat(self.path)
        except OSError:
            self.stat_data = None

        return self.stat_data

    @property
    def md5sum(self):
        return md5sum(self.path)

    def same_as(self, other):
        """Are two filesystem objects the same?"""
        if S_IFMT(self.stat.st_mode) != S_IFMT(other.stat.st_mode):
            # Different fundamental types
            return False
        elif S_ISREG(self.stat.st_mode):
            # Files with the same size and MD5sum are the same
            if self.stat.st_size != other.stat.st_size:
                return False
            return self.md5sum == other.md5sum
        elif S_ISDIR(self.stat.st_mode) or S_ISFIFO(other.stat.st_mode) \
                or S_ISSOCK(self.stat.st_mode):
            # Directories, fifos and sockets are always the same
            return True
        elif S_ISCHR(self.stat.st_mode) or S_ISBLK(other.stat.st_mode):
            # Char/block devices are the same if they have the same rdev
            return self.stat.st_rdev == other.stat.st_rdev
        elif S_ISLNK(self.stat.st_mode):
            # Symbolic links are the same if they have the same target
            return os.readlink(self.path) == os.readlink(other.path)
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
        self.files = {}

        # Specific merge-related information to flag to the maintainer
        self.notes = []

        # Changes pending as part of the merge
        self.pending_changes = {}

        # Changes made relative to the right version
        self.changes_made = {}

        # Files that generated conflicts when merging
        self.conflicts = set()

    def get_file_info(self, path):
        if path not in self.files:
            self.files[path] = FileInfo(path)

        return self.files[path]

    def get_all_file_info(self, filename):
        return (self.get_file_info(os.path.join(self.base_dir, filename)),
                self.get_file_info(os.path.join(self.left_dir, filename)),
                self.get_file_info(os.path.join(self.right_dir, filename)))

    def record_note(self, note, changelog_worthy=False):
        self.notes.append((note, changelog_worthy))

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
        if change_type == 0:
            return

        if filename in self.changes_made:
            assert self.changes_made[filename] == change_type

        self.changes_made[filename] = change_type

    # Record a pending change to make in the merge directory
    def record_pending_change(self, filename, pending_change_type):
        assert filename not in self.pending_changes
        self.pending_changes[filename] = pending_change_type

    # Apply a specific pending change to a file.
    # Return the type of change made, 0 if there was ultimately no change
    # made (relative to right version), or None if it conflicted
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
            base_file_info, left_file_info, right_file_info = \
                self.get_all_file_info(filename)

            # Even though the file was originally enqueued for merge,
            # some of our post-processing might have dropped local
            # changes, in which case we can just use the right
            # version as-is.
            if left_file_info.stat and base_file_info.stat \
                    and left_file_info.same_as(base_file_info):
                # same file contents in left and base, so just copy
                # over the right version
                logger.debug('%s left and base are now the same file',
                             filename)
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
                return 0

            if self.merge_file_contents(filename):
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

            base_file_info, left_file_info, right_file_info = \
                self.get_all_file_info(filename)

            if left_file_info.stat is None and right_file_info.stat is None:
                # Removed on both sides
                pass

            elif left_file_info.stat is None:
                logger.debug("removed from %s: %s", self.left_distro, filename)
                if not base_file_info.same_as(right_file_info):
                    # Changed on RHS
                    self.conflicts.add(filename)
                else:
                    # File was remvoed on left. Put it in place in the merged
                    # dir but record it as a pending deletion.
                    tree.copyfile("%s/%s" % (self.right_dir, filename),
                                  "%s/%s" % (self.merged_dir, filename))
                    self.record_pending_change(filename, self.PENDING_REMOVE)

            elif right_file_info.stat is None:
                # Removed on RHS only
                logger.debug("removed from %s: %s", self.right_distro,
                             filename)
                if not base_file_info.same_as(left_file_info):
                    # Changed on LHS
                    self.record_pending_change(filename, self.PENDING_MERGE)

            elif S_ISREG(left_file_info.stat.st_mode) \
                    and S_ISREG(right_file_info.stat.st_mode):
                # Common case: left and right are both files
                self.handle_file(filename)

            elif left_file_info.same_as(right_file_info):
                # left and right are the same, doesn't matter which we keep
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))

            elif base_file_info.same_as(left_file_info):
                # right has changed in some way, keep that one
                logger.debug("preserving non-file change in %s: %s",
                             self.right_distro, filename)
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))

            elif base_file_info.same_as(right_file_info):
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

            base_file_info, left_file_info, right_file_info = \
                self.get_all_file_info(filename)
 
            if base_file_info.exists:
                continue

            if not right_file_info.exists:
                logger.debug("new in %s: %s", self.left_distro, filename)
                self.record_pending_change(filename, self.PENDING_ADD)
                continue

            if S_ISREG(left_file_info.stat.st_mode) \
                    and S_ISREG(right_file_info.stat.st_mode):
                # Common case: left and right are both files
                self.handle_file(filename)

            elif left_file_info.same_as(right_file_info):
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
        self.handle_control_file('debian/control')
        self.handle_control_in_file()

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

        # If we have a base version, see if diff3 can figure it out cleanly
        if self.diff3_merge(series_file):
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

        try:
            shutil.copy2(os.path.join(self.right_dir, series_file),
                         os.path.join(self.merged_dir, series_file))
        except IOError, e:
            # series file might have been completely dropped on right
            if e.errno == errno.ENOENT:
                pass

        with open(os.path.join(self.merged_dir, series_file), 'a') as fd:
            fd.write(added_data)

        del self.pending_changes[series_file]
        self.record_change(series_file, self.FILE_MODIFIED)
        self.record_note('Downstream additions to quilt series file were '
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

        # Experiment with patch reverts when the right side patches have
        # been applied first
        tmpdir = mkdtemp(prefix='mom.quiltrevert.')
        try:
            os.rmdir(tmpdir)
            shutil.copytree(self.merged_dir, tmpdir, symlinks=True)
            self.__revert_quilt_patches(tmpdir, apply_right=True)
        finally:
            shutil.rmtree(tmpdir)

        # Experiment with patch refreshes under a temporary copy
        tmpdir = mkdtemp(prefix='mom.quiltrefresh.')
        try:
            dest = os.path.join(tmpdir, self.left_name)
            shutil.copytree(self.merged_dir, dest, symlinks=True)
            self.__refresh_quilt_patches(dest)
        finally:
            shutil.rmtree(tmpdir)

    def __revert_quilt_patches(self, tmpdir, apply_right=False):
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

        # Optionally apply all of the patches on the right side, up until
        # we find one of our own patches.
        # This can be used to detect the case when our patch can be reverted
        # because the new upstream version added it as a quilt patch.
        if apply_right:
            proc = subprocess.Popen(['quilt', 'series'],
                                    stdout=subprocess.PIPE,
                                    env={'QUILT_PATCHES': 'debian/patches'},
                                    cwd=tmpdir)
            merged_series, stderr = proc.communicate()
            if proc.returncode != 0:
                logging.debug('quilt series failed in left version')
                return
            merged_series = merged_series.splitlines()

            last_patch = None
            for patch in merged_series:
                patch = os.path.basename(patch)
                if patch in our_added_patches:
                    break
                last_patch = patch

            if last_patch is None:
                return

            logger.debug('Applying upstream series up to %s', last_patch)
            proc = subprocess.Popen(['quilt', 'push', last_patch],
                                    stdout=subprocess.PIPE,
                                    env={'QUILT_PATCHES': 'debian/patches'},
                                    cwd=tmpdir)
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                logger.debug('quilt failed to apply up to last patch %s',
                             last_patch)
                return

        # Revert our patches one by one
        patches_to_drop = []
        for patch in reversed(our_added_patches):
            # Skip if the patch has already been dropped
            if 'debian/patches/' + patch not in self.pending_changes:
                continue

            logging.debug('Trying to revert our patch %s', patch)
            args = ['patch', '--dry-run', '-p1', '--reverse', '-i',
                    os.path.join(self.left_dir, 'debian', 'patches', patch)]
            with open('/dev/null', 'w') as fd:
                rc = subprocess.call(args, cwd=tmpdir, stdout=fd)
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
        self.record_change('debian/patches/series', self.FILE_MODIFIED)

        for patch in patches_to_drop:
            logging.debug('Dropping revertable patch %s', patch)
            del self.pending_changes['debian/patches/' + patch]
            if apply_right:
                self.record_note('Dropped patch %s because it can be reverted '
                                 'cleanly after applying upstream quilt '
                                 'patches' % patch, True)
            else:
                self.record_note('%s: Dropped because it can be reverted '
                                 'cleanly from upstream source' % patch, True)

        if not written:
            logging.debug('No quilt patches remaining, removing directory')
            self.record_note('debian/patches was entirely removed as there '
                             'were no patches remaining.')
            os.unlink(series_file)
            os.rmdir(os.path.join(self.merged_dir, 'debian', 'patches'))
            del self.changes_made['debian/patches/series']

    def __sbtm_refresh(self, patch, patched_files, base_dir, left_dir,
                       merged_dir):
        quiltenv = {'QUILT_PATCHES': 'debian/patches'}

        # Apply all patches in base copy
        if os.path.exists(base_dir + '/debian/patches/series') \
                and os.path.getsize(base_dir + '/debian/patches/series') > 0:
            rc = subprocess.call(['quilt', 'push', '-a', '-q'],
                                 env=quiltenv, cwd=base_dir)
            if rc != 0:
                logger.debug('Failed to apply patches in base dir')
                return False

        # Apply patches in left copy, up to and including this one
        rc = subprocess.call(['quilt', 'push', '-q', patch],
                             env=quiltenv, cwd=left_dir)
        if rc != 0:
            logger.debug('Failed to apply patches in left dir')
            return False

        # Create a new patch where we will store our work
        rc = subprocess.call(['quilt', 'new', 'mommodify.patch'],
                             env=quiltenv, cwd=merged_dir)
        if rc != 0:
            logger.debug('Failed to create new patch')
            return False

        # Add all the files that are to be modified
        rc = subprocess.call(['quilt', 'add'] + patched_files,
                             env=quiltenv, cwd=merged_dir)
        if rc != 0:
            logger.debug('Failed to add files to new patch')
            return False

        # Work on a file-by-file basis
        for filename in patched_files:
            # Use filterdiff piped to patch to attempt to apply the hunks
            # to this given file. If this file can be patched in this way,
            # we do not need to use sbtm.
            args = ['filterdiff', '-p1', filename, patch]
            filterdiff = subprocess.Popen(args, stdout=subprocess.PIPE,
                                          cwd=left_dir)
            patch_proc = subprocess.Popen(['patch', '-p1', '--quiet', '-f'],
                                          stdin=filterdiff.stdout,
                                          cwd=merged_dir)
            patch_proc.communicate()
            if filterdiff.returncode == 0 and patch_proc.returncode == 0:
                logger.debug('Applied patch to %s', filename)
                continue

            # If that failed, try using SBTM to do the merge.
            merged = self.__sbtm_merge(os.path.join(base_dir, filename),
                                       os.path.join(left_dir, filename),
                                       os.path.join(merged_dir, filename))

            # If sbtm fails too, we're out of luck.
            if merged is None:
                logger.debug('sbtm failed on %s', filename)

                return False

            logger.debug('Successfully merged %s with sbtm', filename)
            with open(os.path.join(merged_dir, filename), 'w') as fd:
                fd.write(merged)

        # Write our updated patch out to disk, preserving the original
        # patch header.
        rc = subprocess.call(['quilt', 'refresh'],
                             env=quiltenv, cwd=merged_dir)
        if rc != 0:
            logger.debug('Failed to refresh new patch')
            return False

        try:
            header = subprocess.check_output(['quilt', 'header', patch],
                                             env=quiltenv, cwd=left_dir)
        except CalledProcessError:
            logger.exception('Failed to get %s header', patch)
            return False

        proc = subprocess.Popen(['quilt', 'header', '-r'],
                                stdin=subprocess.PIPE,
                                env=quiltenv, cwd=merged_dir)
        proc.communicate(header)
        if proc.returncode != 0:
            logger.debug('Failed to get %s header', patch)
            return False

        # Save the new patch into the right location
        dest = os.path.join(merged_dir, patch)
        tree.copyfile(merged_dir + '/debian/patches/mommodify.patch', dest)

        # Remove the temporary patch we made
        rc = subprocess.call(['quilt', 'delete', '-r'],
                             env=quiltenv, cwd=merged_dir)
        if rc != 0:
            logger.debug('Failed to remove temporary patch')
            return False

        return True

    # Try to recreate the given patch file using SBTM
    # The given merged_tmp tree is assumed to have all preceeding patches
    # already applied.
    def sbtm_refresh(self, merged_tmp, patch):
        logging.debug('Attempting to refresh %s with SBTM', patch)

        # We can only proceed if all the files affected by the patch
        # exist on the right side too.
        try:
            patched_files = subprocess.check_output(['lsdiff', '--strip=1',
                                                     patch],
                                                    cwd=self.left_dir)
        except CalledProcessError:
            logger.exception('Failed to list %s patched files', patch)
            return False

        patched_files = patched_files.splitlines()
        for filename in patched_files:
            if not os.path.exists(os.path.join(self.right_dir, filename)):
                logger.debug('%s doesn\'t exist on right, skipping patch',
                             filename)
                return False

        # Set up temporary copies of base, left and right which we will
        # use for patch reconstruction
        tmpdir = mkdtemp(prefix='mom.sbtm_refresh.')
        try:
            base_tmp = os.path.join(tmpdir, 'base')
            left_tmp = os.path.join(tmpdir, 'left')
            shutil.copytree(self.base_dir, base_tmp, symlinks=True)
            shutil.copytree(self.left_dir, left_tmp, symlinks=True)
            return self.__sbtm_refresh(patch, patched_files, base_tmp,
                                       left_tmp, merged_tmp)
        finally:
            shutil.rmtree(tmpdir)

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
                rc = subprocess.call(['quilt', 'push', '-q'], **quiltexec)
                if rc != 0:
                    logging.warning('Failed to apply base patch %s', patch)
                    return
                continue

            # Try to apply with no fuzz, like Debian does
            rc = subprocess.call(['quilt', 'push', '-q', '--fuzz=0'],
                                 **quiltexec)
            if rc == 0:
                # Patch applied without fuzz, nothing to do
                logging.debug('%s applied without fuzz, nothing to do', patch)
                continue

            # Try applying with fuzz
            logging.debug('%s failed to apply, trying with fuzz', patch)
            rc = subprocess.call(['quilt', 'push', '-q'], **quiltexec)
            if rc == 0:
                # Patch applies with fuzz, refresh it
                logging.debug('%s now applied, refreshing', patch)
                self.record_note('%s: refreshed to eliminate fuzz' % patch,
                                 True)
                subprocess.check_call(['quilt', 'refresh'], **quiltexec)
                shutil.copy2(os.path.join(tmpdir, patch),
                             os.path.join(self.merged_dir, patch))
                del self.pending_changes[patch]
                self.record_change(patch, self.FILE_ADDED)
                continue

            # Fall back on SBTM reconstruction
            if self.sbtm_refresh(tmpdir, patch) \
                    and subprocess.call(['quilt', 'push', '-q'],
                                        **quiltexec) == 0:
                shutil.copy2(os.path.join(tmpdir, patch),
                             os.path.join(self.merged_dir, patch))
                self.record_note('%s was refreshed with an experimental '
                                 'State-Based Text Merge tool' % patch)
                del self.pending_changes[patch]
                self.record_change(patch, self.FILE_ADDED)
                continue

            logging.debug('%s still failed to apply', patch)
            self.record_note('Our patch %s fails to apply to the new '
                             'version' % patch)

            return

    def handle_control_file(self, control_file):
        if control_file not in self.pending_changes or \
                self.pending_changes[control_file] != self.PENDING_MERGE:
            return

        if not os.path.isfile("%s/%s" % (self.base_dir, control_file)):
            return

        control_merger = DebControlMerger(control_file,
                                          self.left_dir, self.left_name,
                                          self.right_dir, self.right_name,
                                          self.base_dir, self.merged_dir)
        merged = control_merger.run()
        if merged:
            self.merge_attr(control_file)
            if control_merger.modified:
                self.record_change(control_file, self.FILE_MODIFIED)
            del self.pending_changes[control_file]
        for note, changelog_worthy in control_merger.notes:
            self.record_note('%s: %s' % (control_file, note), changelog_worthy)

    def handle_control_in_file(self):
        control_file = 'debian/control.in'

        if control_file not in self.pending_changes or \
                self.pending_changes[control_file] != self.PENDING_MERGE:
            return

        if not os.path.isfile("%s/%s" % (self.base_dir, control_file)):
            return

        if not os.path.isfile("%s/%s" % (self.right_dir, control_file)):
            # If the control file was completely removed on the right,
            # then we can discard our local changes, with the expectation
            # that they were fully represented in debian/control anyway.
            self.record_note('debian/control.in: dropped downstream '
                             'changes because control.in was removed upstream',
                             True)
            del self.pending_changes[control_file]

        # Otherwise fall back on a regular control merge
        self.handle_control_file(control_file)

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

    def handle_file(self, filename):
        """Handle the common case of a file in both left and right."""
        base_file_info, left_file_info, right_file_info = \
            self.get_all_file_info(filename)
        do_attrs = True

        if base_file_info.stat and \
                base_file_info.same_as(left_file_info):
            # same file contents in base and left, meaning that the left
            # side was unmodified, so take the right side as-is
            logger.debug("%s was unmodified on the left", filename)
            tree.copyfile("%s/%s" % (self.right_dir, filename),
                          "%s/%s" % (self.merged_dir, filename))
            self.merge_attr(filename)
        elif left_file_info.same_as(right_file_info):
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
    def merge_file_contents(self, filename):
        base_file_info, left_file_info, right_file_info = \
            self.get_all_file_info(filename)

        if filename == "debian/changelog":
            # two-way merge of changelogs
            try:
                self.merge_changelog(filename)
                return True
            except Exception:
                return False
        elif base_file_info.stat is not None \
                and S_ISREG(base_file_info.stat.st_mode):
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

    def do_diff3(self, filename, output=subprocess.PIPE):
        args = ("diff3", "-E", "-m",
                "-L", self.left_name,
                "%s/%s" % (self.left_dir, filename),
                "-L", "BASE",
                "%s/%s" % (self.base_dir, filename),
                "-L", self.right_name,
                "%s/%s" % (self.right_dir, filename))
        proc = subprocess.Popen(args, stdout=output)
        outdata, errdata = proc.communicate()
        return proc.returncode

    def diff3_merge(self, filename):
        """Merge a file using diff3."""
        base_file_info, left_file_info, right_file_info = \
            self.get_all_file_info(filename)
        if not (base_file_info.stat and left_file_info.stat
                and right_file_info.stat):
            return

        dest = "%s/%s" % (self.merged_dir, filename)
        tree.ensure(dest)

        with open(dest, "w") as output:
            if self.do_diff3(filename, output) == 0:
                return True

        if not tree.exists(dest) or os.stat(dest).st_size == 0:
            # Probably binary
            if left_file_info.same_as(right_file_info):
                logger.debug("binary files are the same: %s", filename)
                tree.copyfile("%s/%s" % (self.left_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
            elif base_file_info.same_as(left_file_info):
                logger.debug("preserving binary change in %s: %s",
                             self.right_distro, filename)
                tree.copyfile("%s/%s" % (self.right_dir, filename),
                              "%s/%s" % (self.merged_dir, filename))
            elif base_file_info.same_as(right_file_info):
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

    def __sbtm_merge(self, base_file, left_file, right_file, fast=False):
        # We run this python app as a separate process as it does a lot of
        # recursion and can cause high memory usage, stack overflow, etc.
        args = [os.path.join(os.path.abspath(os.path.dirname(__file__)),
                             'sbtm.py')]
        if fast:
            args.append('--fast')
        args.extend([base_file, left_file, right_file])

        process = Popen(args,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            return None

        return stdout

    def sbtm_merge(self, filename, fast=False):
        """Merge a file using State-Based Text Merge tool.
        This is experimental and often fails, but has been shown to
        work correctly in some cases.

        The alternate "--fast" algorithm is less likely to exhaust
        recursion limits, but also less likely to produce accurate
        results."""
        dest = "%s/%s" % (self.merged_dir, filename)
        tree.ensure(dest)

        merged = self.__sbtm_merge(os.path.join(self.base_dir, filename),
                                   os.path.join(self.left_dir, filename),
                                   os.path.join(self.right_dir, filename),
                                   fast)
        if merged is None:
            return False

        with open(dest, "w") as output:
            output.write(merged)

        note = '%s was merged with an experimental '\
               'State-Based Text Merge tool' % filename
        if fast:
            note += ' using the fast diff algorithm (particularly prone to ' \
                    'inaccuracies)'
        self.record_note(note)

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
        src_stat = self.get_file_info("%s/%s" % (src_dir, filename)).stat
        base_stat = self.get_file_info("%s/%s" % (base_dir, filename)).stat
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
        base_src = "%s/%s" % (self.base_dir, filename)
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

        if tree.exists(base_src):
            tree.copyfile(base_src, "%s.BASE" % dest)
        if os.path.isdir(base_src):
            os.symlink("%s.BASE" % os.path.basename(dest), dest)

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
