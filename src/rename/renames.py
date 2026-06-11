import logging
import shutil
from collections import Counter
from functools import reduce
from pathlib import Path
from typing import Never

from rename.renames_file import Rename
from rename.renames_file import Renames
from rename.utils import UserError

_ignored_files_when_cleansing_directories = [".DS_Store"]


def _path_to_str(path: Path) -> str:
    if path == Path():
        return ""
    else:
        return f"{path}"


def _common_prefix(path_1: Path, path_2: Path) -> Path:
    assert path_1.root == path_2.root

    for parent_1, parent_2 in reversed(
        list(
            zip(
                [*reversed(path_1.parents), path_1], [*reversed(path_2.parents), path_2]
            )
        )
    ):
        if parent_1 == parent_2:
            return parent_1

    # Roots must be the same.
    assert False


def create_renames(file_paths: list[Path], explicit_base_path: Path | None) -> Renames:
    dirs_by_root: dict[str, set[Path]] = {}

    for i in file_paths:
        dirs_by_root.setdefault(i.root, set()).add(i.parent)

    if explicit_base_path is None:
        base_paths_by_root = {
            k: reduce(_common_prefix, v) for k, v in dirs_by_root.items()
        }
    else:
        base_paths_by_root = {explicit_base_path.root: explicit_base_path}

    renames = []

    for i in file_paths:

        def raise_not_contained_in_base_path() -> Never:
            raise UserError(f"{i} is not contained in base path {explicit_base_path}.")

        base_path = base_paths_by_root.get(i.root)

        if base_path is None:
            raise_not_contained_in_base_path()

        try:
            relative_path = i.relative_to(base_path)
        except ValueError:
            raise_not_contained_in_base_path()

        base_path_str = _path_to_str(base_path)
        dir_str = _path_to_str(relative_path.parent)
        name = relative_path.stem
        suffix = relative_path.suffix

        renames.append(
            Rename(base_path_str, dir_str, name, suffix, dir_str, name, suffix)
        )

    return Renames(renames)


def apply_renames(renames: Renames) -> None:
    moved_files = []
    already_renamed_old_paths = set()
    dirs_to_cleanse: Counter[Path] = Counter()

    def add_dir_to_cleanse(base_path: Path, dir: Path) -> None:
        if base_path in dir.parents:
            if dir not in dirs_to_cleanse:
                add_dir_to_cleanse(base_path, dir.parent)

            dirs_to_cleanse[dir] += 1

    def cleanse_dir(dir: Path) -> None:
        if dirs_to_cleanse[dir]:
            dirs_to_cleanse[dir] -= 1

            if not dirs_to_cleanse[dir]:
                if all(
                    i.name in _ignored_files_when_cleansing_directories
                    and i.is_file(follow_symlinks=False)
                    for i in dir.iterdir()
                ):
                    logging.info(f"Removing directory {dir}.")
                    shutil.rmtree(dir)
                    cleanse_dir(dir.parent)

    for rename in renames.renames:
        base_path = Path(rename.base_path)
        old_path = base_path / rename.old_dir / f"{rename.old_name}{rename.old_suffix}"
        new_path = base_path / rename.new_dir / f"{rename.new_name}{rename.new_suffix}"

        if old_path.exists(follow_symlinks=False):
            if old_path == new_path:
                continue
            elif new_path.exists(follow_symlinks=False):
                if not old_path.samefile(new_path):
                    raise UserError(f"Destination {new_path} already exists.")
        elif not new_path.exists(follow_symlinks=False):
            raise UserError(f"File {old_path} does not exist.")
        else:
            already_renamed_old_paths.add(old_path)

        moved_files.append((old_path, new_path))
        add_dir_to_cleanse(base_path, old_path.parent)

    for old_path, new_path in moved_files:
        if not old_path.exists(follow_symlinks=False):
            if not new_path.exists(follow_symlinks=False):
                raise UserError(f"File {old_path} does not exist.")

            already_renamed_old_paths.add(old_path)

    old_paths = Counter(i for i, _ in moved_files)
    new_paths = Counter(i for _, i in moved_files)

    for i, count in old_paths.items():
        if count > 1:
            raise UserError(f"File {i} is moved to multiple destinations.")

    for i, count in new_paths.items():
        if count > 1:
            raise UserError(f"Multiple files are moved to {i}.")

    for i in set(old_paths).intersection(new_paths):
        raise UserError(f"{i} is both a source and a destination.")

    did_rename = False

    for old_path, new_path in moved_files:
        if old_path not in already_renamed_old_paths:
            if not new_path.parent.exists(follow_symlinks=True):
                logging.info(f"Creating directory at {new_path.parent}.")
                new_path.parent.mkdir(parents=True)

            logging.info(f"Renaming {old_path} to {new_path}.")

            old_path.rename(new_path)
            did_rename = True

        cleanse_dir(old_path.parent)

    if not did_rename:
        logging.info("No files to rename.")
