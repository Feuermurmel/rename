import csv
import logging
import shlex
import sys
from argparse import ArgumentParser
from argparse import Namespace
from collections import Counter
from dataclasses import astuple
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from pathlib import Path
from shlex import quote

from appscript import app
from appscript import k
from appscript import mactypes
from platformdirs import user_data_path


class UserError(Exception):
    pass


@dataclass
class Rename:
    base_path: str
    old_dir: str
    old_name: str
    old_suffix: str
    new_dir: str
    new_name: str
    new_suffix: str

    def reversed(self) -> Rename:
        return Rename(
            self.base_path,
            self.new_dir,
            self.new_name,
            self.new_suffix,
            self.old_dir,
            self.old_name,
            self.old_suffix,
        )


@dataclass
class Renames:
    renames: list[Rename]

    def reversed(self) -> Renames:
        return Renames([i.reversed() for i in self.renames])


rename_file_column_names = [
    "Base Path",
    "Old Path",
    "Old Name",
    "Old Suffix",
    "New Path",
    "New Name",
    "New Suffix",
]


def write_renames_file(path: Path, renames: Renames) -> None:
    with path.open("wt") as file:
        writer = csv.writer(file)
        writer.writerow(rename_file_column_names)
        writer.writerows(map(astuple, renames.renames))


def read_renames_file(path: Path) -> Renames:
    # TODO: Ignore empty lines

    with path.open("rt") as file:
        reader = csv.DictReader(file)
        renames = [Rename(*(i[j] for j in rename_file_column_names)) for i in reader]

        return Renames(renames)


def path_to_str(path: Path) -> str:
    if path == Path():
        return ""
    else:
        return f"{path}"


def common_prefix(path_1: Path, path_2: Path) -> Path:
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


def gather_file_paths(no_traverse: bool, paths: list[Path]) -> list[Path]:
    if no_traverse:
        return paths

    file_paths = []

    for path in paths:
        if path.is_file(follow_symlinks=False):
            file_paths.append(path)
        else:
            for dirpath, dirnames, filenames in path.walk():
                for list in dirnames, filenames:
                    list[:] = sorted(i for i in list if not i.startswith("."))

                for i in filenames:
                    file_path = dirpath / i

                    if file_path.is_file(follow_symlinks=False):
                        file_paths.append(file_path)

    return file_paths


def create_renames(file_paths: list[Path]) -> Renames:
    dirs_by_root: dict[str, set[Path]] = {}

    for i in file_paths:
        dirs_by_root.setdefault(i.root, set()).add(i.parent)

    base_paths_by_root = {k: reduce(common_prefix, v) for k, v in dirs_by_root.items()}
    renames = []

    for i in file_paths:
        base_path = base_paths_by_root[i.root]
        relative_path = i.relative_to(base_path)

        base_path_str = path_to_str(base_path)
        dir_str = path_to_str(relative_path.parent)
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


def edit_csv(csv_path: Path) -> None:
    logging.info(f"Opening {csv_path}.")

    file = mactypes.File(csv_path)
    numbers = app("Numbers")
    document = numbers.open(file)

    try:
        input("ready? ")
    finally:
        numbers.export(document, to=file, as_=k.CSV)
        document.close(saving=k.no)


def parse_args() -> Namespace:
    parser = ArgumentParser()

    action_group = parser.add_mutually_exclusive_group(required=True)

    action_group.add_argument("-a", "--apply", type=Path)
    action_group.add_argument("-r", "--revert", type=Path)
    action_group.add_argument("paths", nargs="*", type=Path)

    parser.add_argument("-d", "--no-traverse", action="store_true")

    args = parser.parse_args()

    if not args.paths and args.no_traverse:
        parser.error("--no-traverse cannot be combined with --apply or --revert.")

    return args


def main(
    apply: Path | None, revert: Path | None, no_traverse: bool, paths: list[Path]
) -> None:
    if apply is not None:
        apply_renames(read_renames_file(apply))
    elif revert is not None:
        apply_renames(read_renames_file(revert).reversed())
    else:
        renames = create_renames(gather_file_paths(no_traverse, paths))

        if not renames.renames:
            raise UserError("No regular files found in paths.")

        csv_file_name = f"rename-{paths[0].name}-{datetime.now():%Y-%m-%d-%H%M%S}.csv"
        csv_file_path = user_data_path("rename", ensure_exists=True) / csv_file_name

        assert not csv_file_path.exists()

        write_renames_file(csv_file_path, renames)

        try:
            edit_csv(csv_file_path)
        except Exception, KeyboardInterrupt:
            logging.warning(
                f"\n"
                f"Editing was interrupted. You can continue editing with "
                f"this command:\n"
                f"{quote(sys.argv[0])} --edit={shlex.quote(str(csv_file_path))}"
            )

            raise

        try:
            apply_renames(read_renames_file(csv_file_path))
        except Exception, KeyboardInterrupt:
            logging.warning(
                f"\n"
                f"Renaming was interrupted. You can continue the operation "
                f"with this command:\n"
                f"{quote(sys.argv[0])} --apply={shlex.quote(str(csv_file_path))}"
            )

            raise
        finally:
            logging.warning(
                f"\n"
                f"The renames can be reverted with this command:\n"
                f"{quote(sys.argv[0])} --revert={shlex.quote(str(csv_file_path))}"
            )


def entry_point() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        main(**vars(parse_args()))
    except UserError as e:
        logging.error(f"error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.error("Operation interrupted.")
        sys.exit(130)
