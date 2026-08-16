
import csv
import json
from io import StringIO
from pathlib import Path


# Resolve the project folder based on this file's location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_json(filename):
    """Load a JSON file and return its parsed Python object."""
    file_path = DATA_DIR / filename

    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_csv(filename):
    """Load a CSV file as a list of dictionaries."""
    file_path = DATA_DIR / filename

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def load_registry_tsv(filename):
    """
    Load the registry TSV.

    The supplied registry contains a trailing comment line beginning with '#'.
    We preserve that comment separately rather than silently dropping it.
    """
    file_path = DATA_DIR / filename

    data_lines = []
    comment_lines = []

    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.startswith("#"):
                comment_lines.append(line.strip())
            else:
                data_lines.append(line)

    reader = csv.DictReader(
        StringIO("".join(data_lines)),
        delimiter="\t"
    )

    records = list(reader)

    return records, comment_lines


def load_source_notes(filename):
   
    file_path = DATA_DIR / filename

    with file_path.open("r", encoding="utf-8") as file:
        return file.read()