import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import sys

import iso8601
import requests


INCOMPLETE_POSTFIX = "_incomplete"
FILENAME_LATEST = "latest"
URL = "http://10.11.99.1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('backup_root', type=Path)
    cli_args = parser.parse_args(sys.argv[1:])

    backup_root = cli_args.backup_root

    if not backup_root.exists():
        raise RuntimeError(f"Backup directory {backup_root} does not exist")

    backup_id = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    symlink = backup_root / FILENAME_LATEST
    previous_directory = symlink.resolve()
    target_directory = backup_root / (backup_id + INCOMPLETE_POSTFIX)

    walk_directory(URL + "/documents/", target_directory, previous_directory)

    final_directory = str(target_directory).replace(INCOMPLETE_POSTFIX, "")
    try:
        target_directory.rename(final_directory)
        print("Renamed directory")
    except FileNotFoundError:
        pass  # nothing was synced
    else:
        try:
            os.remove(symlink)
        except FileNotFoundError:
            pass  # No backup yet
        else:
            os.symlink(final_directory, symlink)


def walk_directory(url, target_directory, previous_directory):

    response = requests.get(url)
    documents = response.json()
    for document in documents:
        name = document['VissibleName']
        target_child = target_directory / name
        previous_child = previous_directory / name
        if document['Type'] == 'CollectionType':
            source_child = url + document['ID'] + "/"
            walk_directory(source_child, target_child, previous_child)
        else:
            download_file(document, target_child, previous_child)


def pdf_filename(file_path):
    return file_path if file_path.suffix else Path(f"{file_path}.pdf")


def download_file(document, target_child, previous_child):
    target_file = pdf_filename(target_child)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {target_file}...")
    response = requests.get(f"{URL}/download/{document['ID']}/placeholder")

    previous_file = pdf_filename(previous_child)
    if previous_file.exists():
        with open(previous_file, 'rb') as file_:
            if contents_unchanged(response.content, file_.read()):
                print(f"Skipping unchanged {target_file}.")
                os.link(previous_file, target_file)

                return

    with open(target_file, 'xb') as file_:
        file_.write(response.content)

    modified = iso8601.parse_date(document['ModifiedClient'])
    change_mtime(target_file, modified)


def contents_unchanged(content1, content2):
    return normalize_pdf(content1) == normalize_pdf(content2)


def normalize_pdf(content):

    return re.sub(
        r"CreationDate\(D\:\d+Z\)", "", content.decode(errors='ignore'),
        count=1)


def change_mtime(target_file: Path, modified: datetime):
    os.utime(target_file, (datetime.now().timestamp(), modified.timestamp()))


if __name__ == "__main__":
    main()
