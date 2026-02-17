import logging
from collections import Counter
from functools import reduce
from pathlib import Path

from rename.renames_file import Rename
from rename.renames_file import Renames
from rename.utils import UserError


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


def create_renames(file_paths: list[Path]) -> Renames:
    dirs_by_root: dict[str, set[Path]] = {}

    for i in file_paths:
        dirs_by_root.setdefault(i.root, set()).add(i.parent)

    base_paths_by_root = {k: reduce(_common_prefix, v) for k, v in dirs_by_root.items()}
    renames = []

    for i in file_paths:
        base_path = base_paths_by_root[i.root]
        relative_path = i.relative_to(base_path)

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

    for rename in renames.renames:
        old_dir = Path(rename.base_path) / rename.old_dir
        old_path = old_dir / f"{rename.old_name}{rename.old_suffix}"
        new_dir = Path(rename.base_path) / rename.new_dir
        new_path = new_dir / f"{rename.new_name}{rename.new_suffix}"

        if old_path.exists(follow_symlinks=False):
            if old_path != new_path:
                if new_path.exists(follow_symlinks=False) and not old_path.samefile(
                    new_path
                ):
                    raise UserError(f"Destination {new_path} already exists.")

                moved_files.append((old_path, new_path))
        elif not new_path.exists(follow_symlinks=False):
            raise UserError(f"File {old_path} does not exist.")

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

    for old_path, new_path in moved_files:
        if not new_path.parent.exists(follow_symlinks=True):
            logging.info(f"Creating directory at {new_path.parent}.")
            new_path.parent.mkdir(parents=True)

        logging.info(f"Renaming {old_path} to {new_path}.")

        old_path.replace(new_path)
