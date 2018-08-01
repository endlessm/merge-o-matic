import os
import logging
from stat import *

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

      if self.merge_file_contents(left_stat, right_stat, base_stat, filename):
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

    both_formats_quilt = self.left_format == self.right_format == "3.0 (quilt)"
    if both_formats_quilt:
        logger.debug("Only merging debian directory since both "
                     "formats 3.0 (quilt)")

    # Look for files in the base and merge them if they're in both new
    # files (removed files get removed)
    for filename in tree.walk(self.base_dir):
        # If both packages are 3.0 (quilt), ignore everything except the
        # debian directory
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
            logger.debug("removed from %s: %s", self.right_distro, filename)
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
    self.handle_po_files()

    # Now apply the remaining changes through simple means
    self.apply_pending_changes()

    for conflict in self.conflicts:
        self.conflict_file(conflict)

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
        shell.run(("msgcat", "--force-po", "--use-first", "-o", merged_pot,
                   right_pot, left_pot))
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
        except:
          return False
    elif filename.endswith(".pot"):
        # two-way merge of pot contents
        return self.merge_pot(filename)
    elif base_stat is not None and S_ISREG(base_stat.st_mode):
        # was file in base: diff3 possible
        return self.diff3_merge(filename)
    else:
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
                            "-L", "BASE", "%s/%s" % (self.base_dir, filename),
                            "-L", self.right_name,
                            "%s/%s" % (self.right_dir, filename)),
                           stdout=output, okstatus=(0,1,2))

    if status != 0:
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
    else:
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
                  [ "u+r", "u+w", "u+x", "g+r", "g+w", "g+x",
                    "o+r", "o+w", "o+x" ][shift])

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
        os.symlink("%s.%s" % (os.path.basename(dest), self.left_distro.upper()),
                   dest)

    if tree.exists(right_src):
        tree.copyfile(right_src, "%s.%s" % (dest, self.right_distro.upper()))
    if os.path.isdir(right_src):
        os.symlink("%s.%s" % (os.path.basename(dest), self.right_distro.upper()),
                   dest)


