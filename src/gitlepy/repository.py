"""Repository module for Gitlepy.
Handles the logic for managing a Gitlepy repository.
All commands from gitlepy.main are dispatched to various functions in this module."""

import pickle
import shutil
import tempfile
from filecmp import cmp
from os import remove
from pathlib import Path
from queue import SimpleQueue
from typing import Dict, List, Optional

from gitlepy.blob import Blob
from gitlepy.commit import Commit
from gitlepy.index import Index


class Repo:
    """A Gitlepy repository object.

    This dataclass provides the variables that represent the repository's
    directory structure within the file system. Its methods further this
    role by serving up various strings and objects constitutive of a repo.

    Args:
        repo_path: Path object representing the working directory.

    Attributes:
        work_dir: The working directory tracked by the repository.
        gitlepy_dir: The gitlepy repository main directory.
        blobs_dir: Where blobs are stored: .gitlepy/blobs
        commits_dir: Where commits are stored: .gitlepy/commits
        branches_dir: Where branch names and their head commits are stored:
            .gitlepy/refs
        index: The file that represents the staging area: .gitlepy/index
        head: The file that references the currently checked out branch:
            .gitlepy/HEAD
        branches (list) : List of branch names.
        commits (list) : List of commit IDs.
        current_branch (str) : Name of the currently checked out branch.

    Methods:
        head_commit_id
        load_commit
        load_index
        load_blob
        get_blobs
        new_commit
        add
        checkout_file
        checkout_branch
        checkout_commit
        merge
    """

    def __init__(self, repo_path: Path):
        self.work_dir: Path = repo_path
        self.gitlepy_dir: Path = Path(self.work_dir / ".gitlepy")
        self.blobs_dir: Path = Path(self.gitlepy_dir / "blobs")
        self.commits_dir: Path = Path(self.gitlepy_dir, "commits")
        self.branches_dir: Path = Path(self.gitlepy_dir, "refs")
        self.index: Path = Path(self.gitlepy_dir, "index")
        self.head: Path = Path(self.gitlepy_dir, "HEAD")

    def branches(self) -> List[str]:
        """Returns a list of branch names."""
        assert self.branches_dir.exists(), (
            "Error: Gitlepy's branches directory does not exist."
        )
        path_list = list(self.branches_dir.glob("*"))
        result = []
        for file in path_list:
            result.append(file.name)
        return result

    def commits(self) -> List[str]:
        """Returns a list of commit ids."""
        if not self.commits_dir.exists():
            print("Error: Gitlepy's commits directory does not exist.")
            raise SystemExit(1)
        path_list = list(self.commits_dir.glob("*"))
        result = []
        for file in path_list:
            result.append(file.name)
        return result

    def current_branch(self) -> str:
        """Returns the name of the currently checked out branch."""
        return self.head.read_text()

    def head_commit_id(self) -> str:
        """Returns the ID of the currrently checked out commit."""
        return Path(self.branches_dir / self.current_branch()).read_text()

    def get_branch_head(self, branch: str) -> str:
        """Returns the head commit ID of the given branch."""
        assert branch in self.branches(), "Not a valid branch name."
        # Define Path object for the branch reference file.
        p = Path(self.branches_dir / branch)
        return p.read_text()

    def load_commit(self, commit_id: str) -> Commit:
        """Returns the Commit object with the specified ID."""
        commit_path = Path(self.commits_dir / commit_id)
        if not commit_path.exists():
            raise SystemExit(1, "Commit object does not exist.")
        with commit_path.open("rb") as file:
            return pickle.load(file)

    def load_index(self) -> Index:
        """Loads the staging area, i.e. the Index object."""
        with self.index.open("rb") as file:
            return pickle.load(file)

    def load_blob(self, blob_id: str) -> Blob:
        p = Path(self.blobs_dir / blob_id)
        with p.open("rb") as file:
            return pickle.load(file)

    def get_blobs(self, commit_id: str) -> Dict[str, str]:
        """Returns the dictionary of blobs belonging to the commit object with the
        specified commit_id.

        Args:
            commit_id: Name of the commit.
        """
        commit_obj = self.load_commit(commit_id)
        return commit_obj.blobs

    def working_files(self) -> list[str]:
        """Returns a list of non-hidden files in the working directory."""
        all_paths: list[Path] = list(self.work_dir.glob("*"))
        working_files = [
            file.name for file in all_paths if not file.name.startswith(".")
        ]
        return working_files

    def untracked_files(self) -> list[str]:
        """Returns a list of files in the working directory that are neither
        tracked by the current commit nor staged for addition; also includes
        files staged for removal and then recreated.
        """
        untracked_files: list[str] = []

        # Create a set of all tracked or staged files.
        tracked_files: set = set(self.get_blobs(self.head_commit_id()).keys())

        index = self.load_index()
        staged_files: set = set(index.additions.keys())

        tracked_files = tracked_files.union(staged_files)

        for file in self.working_files():
            if file not in tracked_files or file in index.removals:
                untracked_files.append(file)

        untracked_files.sort()

        return untracked_files

    def unstaged_modifications(self) -> list[str]:
        """Returns a list of tracked files modified but not staged,
        including a parenthetical indication of whether the file has been
        modified or deleted.

        Such a file is either:
        - tracked in current commit, changed in working directory, but not staged;
        - staged for addition but with different contents than in the working directory;
        - staged for addition but deleted in the working directory;
        - tracked in the current commit and deleted from the working directory,
          but not staged for removal.
        """
        unstaged_files: list[str] = []

        working_files: list[str] = self.working_files()
        tracked_blobs: dict[str, str] = self.get_blobs(self.head_commit_id())

        index: Index = self.load_index()

        for filename in tracked_blobs.keys():
            # File was deleted but not staged for removal
            if self._unstaged_deletion(filename, working_files, index):
                unstaged_files.append(f"{filename} (deleted)")

            # File exists
            elif filename in working_files:
                # First compare with staged file.
                if self._diff_from_staged(filename, index):
                    unstaged_files.append(f"{filename} (modified)")
                # Then compare with unstaged tracked content.
                elif self._unstaged_tracked_modification(
                    filename, index, tracked_blobs
                ):
                    unstaged_files.append(f"{filename} (modified)")

        # Check files staged for addition and untracked.
        for filename in index.additions.keys() - tracked_blobs.keys():
            if filename not in working_files:
                unstaged_files.append(f"{filename} (deleted)")
            elif not self._cmp_blobs(filename, index.additions[filename]):
                unstaged_files.append(f"{filename} (modified)")

        unstaged_files.sort()
        return unstaged_files

    def _unstaged_deletion(
        self, filename, working_files: list[str], index: Index
    ) -> bool:
        """Returns True if the file specified by filename has been deleted but
        not staged for removal.
        """
        return filename not in working_files and filename not in index.removals

    def _diff_from_staged(self, filename: str, index: Index) -> bool:
        """Returns True if the file specified by filename has been modified
        since being staged for addition.
        """
        try:
            return not self._cmp_blobs(filename, index.additions[filename])
        except KeyError:
            return False

    def _unstaged_tracked_modification(
        self, filename: str, index: Index, tracked_blobs: dict[str, str]
    ) -> bool:
        """Returns True if the file is tracked, not staged for addition, and
        has been modified.
        """
        if filename not in index.additions.keys():
            return not self._cmp_blobs(filename, tracked_blobs[filename])
        else:
            return False

    def _cmp_blobs(self, filename: str, blob_id: str) -> bool:
        """Returns true if the file and its corresponding blob are the same.

        This method wraps filecmp.cmp(f1, f2[, shallow=True]) and only adds
        the path to the specified file names before passing them to filecmp.cmp.

        Args:
            filename: Name of the file in the working directory.
            blob_id: Name of the blob file in the blobs directory.
        """
        file = Path(self.work_dir / filename)
        blob = Path(self.blobs_dir / blob_id)
        return cmp(file, blob)

    def new_commit(
        self, parent: str, message: str, merge_parent: Optional[str] = None
    ) -> None:
        """Creates a new Commit object and saves to the repostiory.

        Args:
            parent: ID of the parent commit.
            message: Commit message.
        """
        c = Commit(parent, message, merge_parent)
        c_file = Path.joinpath(self.commits_dir, c.commit_id)

        if parent == "":  # initial commit can be saved immediately
            with c_file.open("wb") as f:
                pickle.dump(c, f)
            self.update_branch_head(self.current_branch(), c.commit_id)
            return

        # Load the index and ensure files are staged for commit.
        index = self.load_index()
        if not index.additions and not index.removals:
            print("No changes staged for commit.")
            raise SystemExit(0)

        # Begin with parent commit's blobs
        c.blobs = self.get_blobs(parent)

        # Remove files staged for removal.
        for key in index.removals:
            c.blobs.pop(key, None)

        # Record files staged for addition.
        c.blobs.update(index.additions)

        # Clear and save index to file system.
        index.clear()
        index.save()

        # Save the commit
        with c_file.open("wb") as f:
            pickle.dump(c, f)

        self.update_branch_head(self.current_branch(), c.commit_id)
        return

    def update_branch_head(self, branch: str, commit_id: str) -> None:
        """Updates the HEAD reference of the specified branch."""
        Path(self.branches_dir / branch).write_text(commit_id)
        return

    def add(self, filename: str) -> None:
        """Stages a file in the working directory for addition.

        If the file to be staged is identical to the one recorded by the
        current commit, then do not stage it.

        Args:
            filename: Name of the file in the working directory to be staged.
        """
        # Create Path object and associated blob
        filepath = Path(self.work_dir / filename)
        new_blob = Blob(filepath)

        # Load the staging area.
        index = self.load_index()

        # Is it unchanged since most recent commit?
        head_commit = self.load_commit(self.head_commit_id())
        if (  # First condition avoids KeyError in blobs dict.
            not filename not in head_commit.blobs.keys()
            and new_blob.id == head_commit.blobs[filename]
        ):
            # Yes -> Do not stage, and remove if already staged.
            if index.is_staged(filename):
                index.unstage(filename)
            else:
                print("No changes have been made to that file.")
        # Check whether file is already staged as well as since changed.
        elif (
            filename in index.additions.keys()
            and new_blob.id == index.additions[filename]
        ):
            print("File is already staged in present state.")
        else:
            # Stage file with blob in the staging area.
            index.stage(filename, new_blob.id)

            # Save the blob.
            blob_path = Path(self.blobs_dir / new_blob.id)
            with blob_path.open("wb") as f:
                f.write(filepath.read_bytes())

        # Save the staging area.
        index.save()

    def remove(self, filename: str) -> None:
        """If the file is staged for addition, unstages it. Otherwise, if
        tracked and not staged, stages it file for removal. If tracked and
        in the working directory, deletes the file.

        Note: does not delete the file if it is untracked.
        """
        index: Index = self.load_index()

        # Check that file is not already staged for removal.
        if filename in index.removals:
            print("That file is already staged for removal.")
            return

        tracked_files = list(self.get_blobs(self.head_commit_id()).keys())

        if filename in index.additions:
            # Stage for removal and save the index.
            index.unstage(filename)
            index.save()
        elif filename in tracked_files:
            index.remove(filename)
            index.save()
            # Delete it if not already deleted.
            file_path = Path(self.work_dir / filename)
            if file_path.exists():
                file_path.unlink()
        else:  # Neither staged nor tracked -> do nothing.
            print("No reason to remove the file.")
            return

    def checkout_file(self, filename: str, target: str = "") -> None:
        """Checks out a file from some commit.

        The default commit is the current HEAD, which is specified by a null
        target.

        Args:
            filename : name of the file to be checked out
            target : commit from which to check out the file
        """
        if target == "":  # Checkout the file from HEAD.
            commit = self.load_commit(self.head_commit_id())
        else:
            commit_id = self._match_commit_id(target)
            if not commit_id:
                print(f"{target} is not a valid commit.")
            else:
                commit = self.load_commit(commit_id)

        # Validate that file exists in target commit.
        if filename not in commit.blobs:
            print(f"{filename} is not a valid file.")
        else:  # Checkout the file
            # Path for file in working directory
            filepath = Path(self.work_dir / filename)
            # Path for the blob
            blob = Path(self.blobs_dir / commit.blobs[filename])
            filepath.write_text(blob.read_text())

    def checkout_branch(self, target: str) -> None:
        """Checks out the given branch.

        target: Name of a branch.
        """
        if target not in self.branches():  # Validate target is a branch.
            print(f"{target} is not a valid branch name.")
        # Don't checkout current branch.
        if target == self.current_branch():
            print(f"Already on '{target}'")
            return

        if self.unstaged_modifications():
            print("There are unstaged modifications in the way; stage and commit them.")
            return

        old_head: str = self.head_commit_id()
        # Update HEAD to reference target branch
        self.head.write_text(target)
        # Checkout the head commit for target branch.
        self._checkout_commit(old_head, self.get_branch_head(target))

    def reset(self, target_id: str) -> None:
        """Resets the current branch to the specified commit."""
        # Validate target as commit id
        target_commit_id = self._match_commit_id(target_id)
        if not target_commit_id:
            print("No commit with that id exists.")
            return

        self._checkout_commit(self.head_commit_id(), target_commit_id)

        # Update current branch HEAD to reference checked out commit.
        current_branch_path = Path(self.branches_dir / self.current_branch())
        current_branch_path.write_text(target_commit_id)

    def _checkout_commit(self, old_head_id: str, target_id: str) -> None:
        """Checks out the given commit.

        This serves both the `gitlepy reset` and the `gitlepy checkout branch`
        commands.

        Unlike git, gitlepy does not allow for a detached HEAD state.
        Instead, checking out an arbitrary commit (via `reset`) resets the
        HEAD of the current branch to that commit.

        Args:
            target_id: id of the commit, can be abbreviated.
        """
        target_blobs: dict = self.get_blobs(target_id)

        # Delete files tracked by current commit and untracked by target commit.
        current_blobs: dict = self.get_blobs(old_head_id)
        for filename in current_blobs.keys():
            if filename not in target_blobs.keys():
                Path(self.work_dir / filename).unlink()

        # Load file contents from blobs.
        for filename in target_blobs.keys():
            file = Path(self.work_dir / filename)
            blob = Path(self.blobs_dir / target_blobs[filename])
            file.write_text(blob.read_text())
            # with open(file, "wt") as f, open(blob, "rb") as b:

        # Update current branch's HEAD ref
        self.update_branch_head(self.current_branch(), target_id)

        # clear the staging area
        index = self.load_index()
        index.clear()
        index.save()

    def _match_commit_id(self, target: str) -> Optional[str]:
        """Determines whether the `target` string is a valid commit.
        If `target` < 40 characters, then it will treat it as an abbreviation
        and try to find a matching commit.
        """
        # if target in commit ids, then return "commit"
        if target in self.commits():
            return target
        # else try to find a match for abbreviate commit id
        elif len(target) < 40:
            matches = []
            for id in self.commits():
                if id.startswith(target):
                    matches.append(id)
            if len(matches) > 1:
                print("Ambiguous commit abbreviation.")
                raise SystemExit(0)
            elif len(matches) == 1:
                return matches[0]
        return None

    def log(self) -> None:
        """Returns a log of the current branch's commit history."""
        history = self._history(self.head_commit_id())
        for id in history:
            commit = self.load_commit(id)
            print(commit)

    def status(self) -> str:
        """Returns a string representation of the repository's current status."""
        output: str = ""
        # Branches
        output = "=== Branches ===\n"
        for branch in self.branches():
            if branch == self.current_branch():
                output += "*"
            output += f"{branch}\n"

        # Staging Area
        index = self.load_index()
        # Staged Files
        output += "\n=== Staged Files ===\n"
        for file in index.additions:
            output += f"{file}\n"
        # Removed Files
        output += "\n=== Removed Files ===\n"
        for file in index.removals:
            output += f"{file}\n"

        # Modifications Not Staged For Commit
        output += "\n=== Modifications Not Staged For Commit ===\n"
        for file in self.unstaged_modifications():
            output += f"{file}\n"
        # Untracked Files
        output += "\n=== Untracked Files ===\n"
        for file in self.untracked_files():
            output += f"{file}\n"

        return output

    def merge(self, target: str) -> None:
        """Merges the current branch with the specified `target` branch.
        It treats the current branch head as the parent commit, and then
        by comparing files between the split-point commit, the HEAD commit,
        and the head of the given branch, it stages files for addition or
        removal before creating a new commit.
        """
        # Validate the merge: True means invalid.
        if self._validate_merge(target):
            return

        # Get target branch's head commit id.
        target_commit_id = self.get_branch_head(target)

        # Get each branch's history and validate.
        current_history: list = self._history(self.head_commit_id())
        target_history: list = self._history(target_commit_id)
        if self._validate_history(target_commit_id, current_history, target_history):
            return

        # Find most recent common ancestor.
        split_id: str = self._find_split(current_history, target_history)
        if split_id == "":
            print("No common ancestor found.")
            return

        # Populate the staging area for the merge commit, and checkout
        # files as necessary. Returns a list of merge conflicts.
        conflicts: list[str] = self._prepare_merge(target_commit_id, split_id)

        if conflicts:
            self._merge_conflict(conflicts, target)
        else:
            merge_message = f"Merged {target} into {self.current_branch()}"
            self.new_commit(self.head_commit_id(), merge_message, target_commit_id)
            print(merge_message)

    def _validate_merge(self, target: str) -> bool:
        """Error checking for merge method. Returns True if invalid.

        Unlike Gitlet, Gitlepy does not overwrite untracked files during
        a merge. Therefore, it does not consider untracked files to be
        in the way of a merge.
        """
        # Check for unstaged modifications files.
        if self.unstaged_modifications():
            print(
                "There is a file with unstaged changes;"
                + " delete it, or add and commit it first."
            )
            return True

        # Check whether staging area is clear.
        index: Index = self.load_index()
        if index.additions or index.removals:
            print("You have uncommitted changes.")
            return True
        # Ensure not already checked out.
        if target == self.current_branch():
            print("Cannot merge a branch with itself.")
            return True
        # Check that the specified branch exists.
        if target not in self.branches():
            print("A branch with that name does not exist.")
            return True

        return False

    def _history(self, head_id: str) -> list[str]:
        """Returns a list of commit IDs composing the specified commit's
        history.

        In order to accommodate merge commits, which have two parents,
        this method uses a queue to interlink divergent branch histories.
        """
        history = []
        q: SimpleQueue = SimpleQueue()
        q.put(head_id)

        while not q.empty():
            current_id = q.get()
            if current_id not in history:
                history.append(current_id)
                current_commit: Commit = self.load_commit(current_id)
                if current_commit.parent_two:
                    q.put(current_commit.parent_two)
                if current_commit.parent_one:
                    q.put(current_commit.parent_one)

        return history

    def _validate_history(
        self, target_head: str, current_history: list[str], target_history: list[str]
    ) -> bool:
        """Returns True if merge should be cancelled. First checks whether the
        target branch is an unmodified ancestor of the current branch. If the
        target branch history contains the current HEAD, then the current
        branch is fast-forwarded by checking out the target branch.

        Args:
            target_head: head commit id of the branch being merged.
            current_history: commit history of the currently checked out branch.
            target_history: commit history of the branch being merged.
        """
        if target_head in current_history:
            print("Target branch is an ancestor of the current branch.")
            return True
        if self.head_commit_id() in target_history:
            print("Current branch is fast-forwarded.")
            self._checkout_commit(self.head_commit_id(), target_head)
            return True
        return False

    def _find_split(self, current_history: list[str], target_history: list[str]) -> str:
        """Returns the most recent common ancestor of the two specified
        commit histories.
        """
        for id in target_history:
            if id in current_history:
                return id

        return ""

    def _prepare_merge(self, target_commit_id: str, split_id: str) -> list[str]:
        """Prepares the staging area for a merge commit and returns a list
        of conflicted files.

        Args:
            target_commit_id: ID of the commit at the head of the branch to be merged.
            split_id: ID of the most recent commont ancestor commit.
        """
        conflicts: list[str] = []
        head_blobs: Dict[str, str] = self.get_blobs(self.head_commit_id())
        target_blobs: Dict[str, str] = self.get_blobs(target_commit_id)
        split_blobs: Dict[str, str] = self.get_blobs(split_id)

        for filename in head_blobs:
            head_blob = head_blobs[filename]

            if filename in target_blobs:  # file tracked by target branch
                self._merge_head_target(
                    conflicts,
                    filename,
                    head_blobs[filename],
                    target_blobs[filename],
                    split_blobs,
                )
            elif filename in split_blobs:
                # Not in target branch and present at split means
                # removed from target branch.
                split_blob = split_blobs[filename]
                # If unmodified in HEAD since split, then remove.
                if head_blob == split_blob:
                    index: Index = self.load_index()
                    index.remove(filename)
                    index.save()
                    Path(self.work_dir / filename).unlink()
            # Remove file from target_blobs
            target_blobs.pop(filename, None)

        # Check files in target branch, which are not in current branch's HEAD.
        # (I.e. all [filename, blob_id] pairs remaining.)
        self._merge_target_blobs(target_blobs, split_blobs, target_commit_id)

        return conflicts

    def _merge_head_target(
        self,
        conflicts: list[str],
        filename: str,
        head_blob_id: str,
        target_blob_id: str,
        split_blobs: dict[str, str],
    ) -> None:
        """Helper method for _prepare_merge() that handles files tracked
        by both the current branch and the target branch.
        """
        index: Index = self.load_index()
        # Check for file at split point
        if filename in split_blobs:
            split_blob_id: str = split_blobs[filename]
            if split_blob_id != target_blob_id:  # Modified in target branch.
                # Not modified in current HEAD -> keep target version.
                if head_blob_id == split_blob_id:
                    index.stage(filename, target_blob_id)
                    index.save()
                # Modified in HEAD -> check for conflict.
                elif head_blob_id != target_blob_id:
                    conflicts.append(filename)
        elif head_blob_id != target_blob_id:  # Not in split commit.
            conflicts.append(filename)

    def _merge_target_blobs(
        self,
        target_blobs: dict[str, str],
        split_blobs: dict[str, str],
        target_commit_id: str,
    ) -> None:
        index: Index = self.load_index()
        for filename in target_blobs:
            target_blob_id = target_blobs[filename]
            if filename not in split_blobs:  # Only present in target branch.
                self.checkout_file(filename, target_commit_id)
                index.stage(filename, target_blob_id)
            elif target_blob_id != split_blobs[filename]:
                index.stage(filename, target_blob_id)

        index.save()

    def _merge_conflict(self, conflicts: list[str], target_branch: str) -> None:
        """Resolves files in conflict by concatenating the two, stages them,
        and then creates a merge commit.
        """
        target_blobs: Dict[str, str] = self.get_blobs(
            self.get_branch_head(target_branch)
        )

        for filename in conflicts:
            head_file = Path(self.work_dir / filename)
            target_blob = Path(self.blobs_dir / target_blobs[filename])

            self._write_conflict(
                head_file, target_blob, self.get_branch_head(target_branch)
            )

            self.add(filename)

        merge_message = f"Merged {self.current_branch()} into {target_branch}."
        self.new_commit(
            self.head_commit_id(), merge_message, self.get_branch_head(target_branch)
        )
        print("Encountered a merge conflict.")

    def _write_conflict(self, head_file: Path, target_blob: Path, commit_id: str):
        """Combines two files in conflict, writing to head_file.

        With the head file as f1 and target file as f2:
        0. Both line1 and line2 exist:
        1. line1 == line2 -> copy as is
        2. line1 != line2
            ->  scan file_2 for matching line
                2a. match found -> insertion: insert lines from file_2 until match
                2b. no match -> Still could be a match in file_2 with remaining
                                file_1 lines.
                2b1. later match -> Start HEAD diff section, copy file_1 lines up
                                   to matching line_1. Mid diff. Repeat for file_2
                                   lines. Loop back to top, which will copy matched
                                   lines.
                2b2. never match -> Start HEAD diff section, copy remaining lines
                                    from file_1, then split diff to remaining
                                    lines in file_2, conclude with end of diff.

        Clean up remaining lines:
            1. If from file_1, then simply copy over.
            2. If from file_2, then add an empty HEAD diff section before copying.
        """
        start_diff = "<<<<<<< HEAD\n"
        mid_diff = "=======\n"
        end_diff = f">>>>>>> {commit_id}\n"

        with (
            head_file.open() as f1,
            target_blob.open() as f2,
            tempfile.NamedTemporaryFile(mode="w+t", delete=False) as temp,
        ):
            seek1 = f1.tell()  # starting positions
            seek2 = f2.tell()
            line1 = f1.readline()  # first lines
            line2 = f2.readline()

            while line1 and line2:
                if line1 == line2:
                    temp.write(line1)
                else:  # Scan f2 for later match to line1
                    skip = False  # For breaking out of top while loop
                    while line2:
                        line2 = f2.readline()
                        if line1 == line2:
                            # Match found -> insert lines from f2 until match.
                            # First reset f2 to non-matching position.
                            f2.seek(seek2)
                            line2 = f2.readline()
                            # Diff section for new f2 lines.
                            temp.write(start_diff)
                            temp.write(mid_diff)
                            while line1 != line2:
                                temp.write(line2)
                                line2 = f2.readline()
                            temp.write(end_diff)
                            # Back to line1 == line2
                            # Continue and let top of loop handle matching lines.
                            skip = True
                            break
                    if skip:
                        skip = False
                        continue

                    # No match to line1 found later in f2, check rest of f1 for
                    # match with any remaining line in f2.
                    f2.seek(seek2)  # First, reset f2 to previous position.
                    line2 = f2.readline()
                    match_byte = self._binsearch_lines(f1, f2)

                    if match_byte > 0:  # Match in f1 found for line2.
                        f1.seek(seek1)  # Reset position of f1.
                        temp.write(start_diff)
                        temp.write(f1.read(match_byte - seek1))  # copy up to match
                        temp.write(mid_diff)
                        # Get matching line from f1.
                        seek1 = f1.tell()
                        line1 = f1.readline()
                        # Copy from f2 up to match.
                        while line1 != line2:
                            temp.write(line2)
                            seek2 = f2.tell()
                            line2 = f2.readline()
                        temp.write(end_diff)
                        # Back to line1 == line2
                        continue
                    else:  # No more matching lines. Finish diff.
                        temp.write(start_diff)
                        f1.seek(seek1)
                        f2.seek(seek2)
                        temp.write(f1.read())
                        temp.write(mid_diff)
                        temp.write(f2.read())
                        temp.write(end_diff)
                        # Advance lines so avoid extraneous writing.
                        line1 = f1.readline()
                        line2 = f2.readline()
                        break

                # Advance to next line, recording its starting position.
                seek1 = f1.tell()
                seek2 = f2.tell()
                line1 = f1.readline()
                line2 = f2.readline()

            # Outside of main while loop.
            # Include trailing lines if any remain.
            if line1:
                temp.write(line1)
                while line1:
                    line1 = f1.readline()
                    temp.write(line1)
            elif line2:
                temp.write(start_diff)
                temp.write(mid_diff)
                temp.write(line2)
                while line2:
                    line2 = f1.readline()
                    temp.write(line2)
                temp.write(end_diff)

        shutil.copy(temp.name, head_file)
        remove(temp.name)

    def _binsearch_lines(self, f1, f2) -> int:
        """Returns the byte location of a matching line in f1 if it exists."""
        # Sort remaining lines in file 2.
        seek2 = f2.tell()
        sorted_f2 = sorted(f2.readlines())  # sort remaining lines in f2
        f2.seek(seek2)  # reset position of f2

        # Iterate over remainig lines in file 1, searching for match in file 2.
        seek1 = f1.tell()
        line = f1.readline()
        while line:
            # When a match is found, return the byte position of the f1 line.
            if self._binsearch(line, sorted_f2):
                return seek1
            seek1 = f1.tell()
            line = f1.readline()

        return 0

    def _binsearch(self, line: str, all_lines: list[str]) -> bool:
        """Helper function for binsearch_lines."""
        if len(all_lines) - 1 >= 0:
            mid: int = (len(all_lines) - 1) // 2

            if line == all_lines[mid]:
                return True
            elif line < all_lines[mid]:
                return self._binsearch(line, all_lines[:mid])
            elif line > all_lines[mid]:
                return self._binsearch(line, all_lines[mid + 1 :])

        return False
