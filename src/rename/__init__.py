import logging
import shlex
import sys
from argparse import ArgumentParser
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from shlex import quote

from platformdirs import user_data_path

from rename.renames import apply_renames
from rename.renames import create_renames
from rename.renames_file import Rename
from rename.renames_file import Renames
from rename.renames_file import read_renames_file
from rename.renames_file import write_renames_file
from rename.utils import UserError
from rename.utils import edit_csv


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
