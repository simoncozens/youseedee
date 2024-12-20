import argparse
import sys
from filelock import FileLock

from youseedee import ucd_data, _download_files, ucd_dir


def main(args=None):
    parser = argparse.ArgumentParser(description="Get Unicode Character Data")
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force download of latest Unicode data",
    )
    parser.add_argument(
        "char",
        type=str,
        help="The character to get data for (either hex codepoint or character)",
    )

    args = parser.parse_args(args)
    if args.force_download:
        file_lock = FileLock(ucd_dir() / ".youseedee_ensure_files.lock")
        with file_lock:
            _download_files()
    char = sys.argv[1]
    if len(char) > 1:
        try:
            if (
                char.startswith("U+")
                or char.startswith("u+")
                or char.startswith("0x")
                or char.startswith("0X")
            ):
                codepoint = int(char[2:], 16)
            else:
                codepoint = int(char, 16)
        except ValueError:
            print("Could not understand codepoint " + char)
            sys.exit(1)
    else:
        codepoint = ord(char)
    data = ucd_data(codepoint)

    print(f"\nCharacter data for '{chr(codepoint)}' (U+{codepoint:04X}, {codepoint})\n")

    for key, value in data.items():
        key = key.replace("_", " ")
        print(f"{key:40} {value}")


if __name__ == "__main__":
    main()
