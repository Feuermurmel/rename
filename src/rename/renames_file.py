from __future__ import annotations

import csv
from dataclasses import astuple
from dataclasses import dataclass
from pathlib import Path


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
