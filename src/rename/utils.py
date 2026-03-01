import logging
import re
from pathlib import Path

from appscript import app
from appscript import k
from appscript import mactypes


class UserError(Exception):
    pass


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


def numeric_sort_key(value: str) -> list[tuple[str, int]]:
    return [
        (i[1], int(i[2] or 0)) for i in re.finditer("(?!$)([^0-9]*)([0-9]*)", value)
    ]
