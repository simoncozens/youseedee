"""Python interface to the Unicode Character Database"""

import bisect
import csv
import datetime
import logging
import re
import sys
import time
import zipfile
from pathlib import Path

import platformdirs
import requests
from filelock import FileLock

log = logging.getLogger(__name__)

try:
    from tqdm import tqdm

    wrapattr = tqdm.wrapattr
except ImportError:

    def wrapattr(x, _y, **_kwargs):
        return x


def bisect_key(haystack, needle, key):
    if sys.version_info[0:2] >= (3, 10):
        return bisect.bisect_right(haystack, needle, key=key)
    haystack = [key(h) for h in haystack]
    return bisect.bisect_right(haystack, needle)


UCD_URL = "https://unicode.org/Public/UCD/latest/ucd/UCD.zip"


def ucd_dir():
    """Return the directory where Unicode data is stored"""
    return Path(platformdirs.user_cache_dir("youseedee", ensure_exists=True))


def ensure_files():
    """Ensure the Unicode data files are downloaded and up to date, and download them if not"""
    file_lock = FileLock(ucd_dir() / ".youseedee_ensure_files.lock")
    with file_lock:
        if not (ucd_dir() / "UnicodeData.txt").is_file():
            _download_files()
        if not _up_to_date():
            # Remove the zip if it exists
            (ucd_dir() / "UCD.zip").unlink(missing_ok=True)
            _download_files()


def _up_to_date():
    """Check if the Unicode data is up to date

    Risks data race across processes without being done within a lock"""
    data_date = (ucd_dir() / "UnicodeData.txt").stat().st_mtime
    # OK if it's less than three months old
    if time.time() - data_date < 60 * 60 * 24 * 30 * 3:
        log.debug("Youseedee data is less than three months old")
        return True
    # Let's check if Unicode has anything newer:
    try:
        response = requests.head(UCD_URL, timeout=5)
    except requests.RequestException as e:
        log.warning("Error checking Unicode update: %s", e)
        return True  # I mean technically it's as up to date as we can get
    if "Last-Modified" not in response.headers:
        log.warning("Could not detect when Unicode last updated, updating anyway")
        return True
    last_modified = response.headers["Last-Modified"]
    available = datetime.datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z")
    return available.timestamp() < data_date


def _download_files():
    """Download the Unicode Character Database files

    Risks data race across processes without being done within a lock"""
    zip_path = ucd_dir() / "UCD.zip"
    if not zip_path.is_file():
        log.info("Downloading Unicode Character Database")
        response = requests.get(UCD_URL, stream=True, timeout=1000)
        with wrapattr(
            open(zip_path, "wb"),
            "write",
            miniters=1,
            total=int(response.headers.get("content-length", 0)),
        ) as fout:
            for chunk in response.iter_content(chunk_size=4096):
                fout.write(chunk)
            fout.close()

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(ucd_dir())


## File parsing functions


def parse_file_ranges(filename):
    """Parse a Unicode file with ranges, such as `Blocks.txt`"""
    ensure_files()
    ranges = []
    with open(ucd_dir() / filename, "r", encoding="utf-8") as f:
        for line in f:
            if re.match(r"^\s*#", line):
                continue
            if re.match(r"^\s*$", line):
                continue
            line = re.sub("#.*", "", line)
            matches = re.match(
                r"^([0-9A-F]{4,})(?:\.\.([0-9A-F]{4,}))?\s*;\s*([^;]+?)\s*$", line
            )
            if not matches:
                continue
            start, end, content = matches.groups()
            if end is None:
                end = start
            ranges.append((int(start, 16), int(end, 16), content))
    return ranges


def parse_file_semicolonsep(filename):
    """Parse a semi-colon separated Unicode file, such as `UnicodeData.txt`"""
    ensure_files()
    data = {}
    with open(ucd_dir() / filename, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";", skipinitialspace=True)
        for row in reader:
            if len(row) < 2:
                continue
            if re.match("^#", row[0]):
                continue
            row[-1] = re.sub(r"\s*#.*", "", row[-1])
            row[0] = int(row[0], 16)  # type: ignore
            data[row[0]] = row[1:]
    return data


def parsed_unicode_file(filename):
    """Return the parsed data for a given Unicode file

    This function will parse the file if it hasn't been parsed yet,
    and return the parsed data. The filename is the full filename
    from the zip file. e.g. `ArabicShaping.txt`. The data is stored
    in a singleton dictionary, so it will only be parsed once.
    """
    fileentry = database[filename]
    if "data" in fileentry:
        return fileentry["data"]
    data = fileentry["reader"](filename)
    # Things we will bisect need to be sorted
    # pylint: disable=comparison-with-callable
    if fileentry["datareader"] == rangereader:
        data = sorted(data, key=lambda x: x[0])
    fileentry["data"] = data
    return data


## Data reading functions; i.e. how to get what you want
## from the parsed data


def dictget(filename, codepoint):
    data = parsed_unicode_file(filename)
    if not codepoint in data:
        return {}
    d = data[codepoint]
    r = {}
    for ix, p in enumerate(database[filename]["properties"]):
        if p == "IGNORE":
            continue
        r[p] = d[ix]
    return r


def rangereader(filename, codepoint):
    data = parsed_unicode_file(filename)
    range_index = bisect_key(data, codepoint, key=lambda x: x[0])
    rangerow = data[range_index - 1]
    start, end = rangerow[0], rangerow[1]
    if codepoint >= start and codepoint <= end:
        data = rangerow[2:]
        r = {}
        for ix, p in enumerate(database[filename]["properties"]):
            if p == "IGNORE":
                continue
            r[p] = data[ix]
        return r
    return {}


database = {
    "ArabicShaping.txt": {
        "properties": ["IGNORE", "Joining_Type", "Joining_Group"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "BidiBrackets.txt": {
        "properties": ["Bidi_Paired_Bracket", "Bidi_Paired_Bracket_Type"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "BidiMirroring.txt": {
        "properties": ["Bidi_Mirroring_Glyph"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "Blocks.txt": {
        "properties": ["Block"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "CaseFolding.txt": {
        "properties": ["Case_Folding_Status", "Case_Folding_Mapping"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "DerivedAge.txt": {
        "properties": ["Age"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "EastAsianWidth.txt": {
        "properties": ["East_Asian_Width"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "HangulSyllableType.txt": {
        "properties": ["Hangul_Syllable_Type"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "IndicPositionalCategory.txt": {
        "properties": ["Indic_Positional_Category"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "IndicSyllabicCategory.txt": {
        "properties": ["Indic_Syllabic_Category"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "Jamo.txt": {
        "properties": ["Jamo_Short_Name"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "LineBreak.txt": {
        "properties": ["Line_Break"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "NameAliases.txt": {
        "properties": ["Name_Alias"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "Scripts.txt": {
        "properties": ["Script"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "ScriptExtensions.txt": {
        "properties": ["Script_Extensions"],
        "reader": parse_file_ranges,
        "datareader": rangereader,
    },
    "SpecialCasing.txt": {
        "properties": ["Uppercase_Mapping", "Lowercase_Mapping", "Titlecase_Mapping"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "UnicodeData.txt": {
        "properties": ["Name", "General_Category", "Canonical_Combining_Class"],
        "reader": parse_file_semicolonsep,
        "datareader": dictget,
    },
    "USECategory.txt": {"properties": ["USE_Category"], "datareader": rangereader},
}


def ucd_data(codepoint):
    """Return a dictionary of Unicode data for a given codepoint

    This is the main function of the module. It will return a dictionary
    of Unicode data for a given codepoint. The codepoint is expected to
    be an integer.
    """
    out = {}
    for file, props in database.items():
        out.update(props["datareader"](file, codepoint))
    return out


database["USECategory.txt"]["data"] = (
    (0x002D, 0x002D, "GB"),
    (0x0030, 0x0039, "B"),
    (0x00A0, 0x00A0, "GB"),
    (0x00B2, 0x00B3, "FMPst"),
    (0x00D7, 0x00D7, "GB"),
    (0x0640, 0x07EA, "B"),
    (0x07EB, 0x07F3, "VMAbv"),
    (0x07FA, 0x07FA, "B"),
    (0x07FD, 0x07FD, "VMAbv"),
    (0x0840, 0x0858, "B"),
    (0x0859, 0x085B, "CMBlw"),
    (0x0900, 0x0902, "VMAbv"),
    (0x0903, 0x0903, "VMPst"),
    (0x0904, 0x0939, "B"),
    (0x093A, 0x093A, "VAbv"),
    (0x093B, 0x093B, "VPst"),
    (0x093C, 0x093C, "CMBlw"),
    (0x093D, 0x093D, "B"),
    (0x093E, 0x093E, "VPst"),
    (0x093F, 0x093F, "VPre"),
    (0x0940, 0x0940, "VPst"),
    (0x0941, 0x0944, "VBlw"),
    (0x0945, 0x0948, "VAbv"),
    (0x0949, 0x094C, "VPst"),
    (0x094D, 0x094D, "H"),
    (0x094E, 0x094E, "VPre"),
    (0x094F, 0x094F, "VPst"),
    (0x0951, 0x0951, "VMAbv"),
    (0x0952, 0x0952, "VMBlw"),
    (0x0953, 0x0954, "O"),
    (0x0955, 0x0955, "VAbv"),
    (0x0956, 0x0957, "VBlw"),
    (0x0958, 0x0961, "B"),
    (0x0962, 0x0963, "VBlw"),
    (0x0966, 0x097F, "B"),
    (0x0980, 0x0980, "GB"),
    (0x0981, 0x0981, "VMAbv"),
    (0x0982, 0x0983, "VMPst"),
    (0x0985, 0x09B9, "B"),
    (0x09BC, 0x09BC, "CMBlw"),
    (0x09BD, 0x09BD, "B"),
    (0x09BE, 0x09BE, "VPst"),
    (0x09BF, 0x09BF, "VPre"),
    (0x09C0, 0x09C0, "VPst"),
    (0x09C1, 0x09C4, "VBlw"),
    (0x09C7, 0x09CC, "VPre"),
    (0x09CD, 0x09CD, "H"),
    (0x09CE, 0x09CE, "IND"),
    (0x09D7, 0x09D7, "VPst"),
    (0x09DC, 0x09E1, "B"),
    (0x09E2, 0x09E3, "VBlw"),
    (0x09E6, 0x09FC, "B"),
    (0x09FE, 0x09FE, "FMAbv"),
    (0x0A01, 0x0A02, "VMAbv"),
    (0x0A03, 0x0A03, "VMPst"),
    (0x0A05, 0x0A39, "B"),
    (0x0A3C, 0x0A3C, "CMBlw"),
    (0x0A3E, 0x0A3E, "VPst"),
    (0x0A3F, 0x0A3F, "VPre"),
    (0x0A40, 0x0A40, "VPst"),
    (0x0A41, 0x0A42, "VBlw"),
    (0x0A47, 0x0A4C, "VAbv"),
    (0x0A4D, 0x0A4D, "H"),
    (0x0A51, 0x0A51, "VMBlw"),
    (0x0A59, 0x0A6F, "B"),
    (0x0A70, 0x0A70, "VMAbv"),
    (0x0A71, 0x0A71, "CMAbv"),
    (0x0A72, 0x0A73, "GB"),
    (0x0A75, 0x0A75, "MBlw"),
    (0x0A81, 0x0A82, "VMAbv"),
    (0x0A83, 0x0A83, "VMPst"),
    (0x0A85, 0x0AB9, "B"),
    (0x0ABC, 0x0ABC, "CMBlw"),
    (0x0ABD, 0x0ABD, "B"),
    (0x0ABE, 0x0ABE, "VPst"),
    (0x0ABF, 0x0ABF, "VPre"),
    (0x0AC0, 0x0AC0, "VPst"),
    (0x0AC1, 0x0AC4, "VBlw"),
    (0x0AC5, 0x0AC9, "VAbv"),
    (0x0ACB, 0x0ACC, "VPst"),
    (0x0ACD, 0x0ACD, "H"),
    (0x0AE0, 0x0AE1, "B"),
    (0x0AE2, 0x0AE3, "VBlw"),
    (0x0AE6, 0x0AF9, "B"),
    (0x0AFA, 0x0AFC, "VMAbv"),
    (0x0AFD, 0x0AFF, "CMAbv"),
    (0x0B01, 0x0B01, "VMAbv"),
    (0x0B02, 0x0B03, "VMPst"),
    (0x0B05, 0x0B39, "B"),
    (0x0B3C, 0x0B3C, "CMBlw"),
    (0x0B3D, 0x0B3D, "B"),
    (0x0B3E, 0x0B3E, "VPst"),
    (0x0B3F, 0x0B3F, "VAbv"),
    (0x0B40, 0x0B40, "VPst"),
    (0x0B41, 0x0B44, "VBlw"),
    (0x0B47, 0x0B4C, "VPre"),
    (0x0B4D, 0x0B4D, "H"),
    (0x0B55, 0x0B57, "VAbv"),
    (0x0B5C, 0x0B61, "B"),
    (0x0B62, 0x0B63, "VBlw"),
    (0x0B66, 0x0B71, "B"),
    (0x0B82, 0x0B82, "VMAbv"),
    (0x0B83, 0x0B83, "IND"),
    (0x0B85, 0x0BB9, "B"),
    (0x0BBE, 0x0BBF, "VPst"),
    (0x0BC0, 0x0BC0, "VAbv"),
    (0x0BC1, 0x0BC2, "VPst"),
    (0x0BC6, 0x0BCC, "VPre"),
    (0x0BCD, 0x0BCD, "H"),
    (0x0BD7, 0x0BD7, "VPst"),
    (0x0BE6, 0x0BEF, "B"),
    (0x0C00, 0x0C00, "VMAbv"),
    (0x0C01, 0x0C03, "VMPst"),
    (0x0C04, 0x0C04, "VMAbv"),
    (0x0C05, 0x0C3D, "B"),
    (0x0C3E, 0x0C40, "VAbv"),
    (0x0C41, 0x0C44, "VPst"),
    (0x0C46, 0x0C4C, "VAbv"),
    (0x0C4D, 0x0C4D, "H"),
    (0x0C55, 0x0C55, "VAbv"),
    (0x0C56, 0x0C56, "VBlw"),
    (0x0C58, 0x0C61, "B"),
    (0x0C62, 0x0C63, "VBlw"),
    (0x0C66, 0x0C80, "B"),
    (0x0C81, 0x0C81, "VMAbv"),
    (0x0C82, 0x0C83, "VMPst"),
    (0x0C85, 0x0CB9, "B"),
    (0x0CBC, 0x0CBC, "CMBlw"),
    (0x0CBD, 0x0CBD, "B"),
    (0x0CBE, 0x0CBE, "VPst"),
    (0x0CBF, 0x0CC0, "VAbv"),
    (0x0CC1, 0x0CC4, "VPst"),
    (0x0CC6, 0x0CCC, "VAbv"),
    (0x0CCD, 0x0CCD, "H"),
    (0x0CD5, 0x0CD6, "VPst"),
    (0x0CDE, 0x0CE1, "B"),
    (0x0CE2, 0x0CE3, "VBlw"),
    (0x0CE6, 0x0CEF, "B"),
    (0x0CF1, 0x0CF2, "CS"),
    (0x0D00, 0x0D01, "VMAbv"),
    (0x0D02, 0x0D03, "VMPst"),
    (0x0D04, 0x0D3A, "B"),
    (0x0D3B, 0x0D3C, "VAbv"),
    (0x0D3D, 0x0D3D, "B"),
    (0x0D3E, 0x0D42, "VPst"),
    (0x0D43, 0x0D44, "VBlw"),
    (0x0D46, 0x0D4C, "VPre"),
    (0x0D4D, 0x0D4D, "H"),
    (0x0D4E, 0x0D4E, "R"),
    (0x0D54, 0x0D56, "IND"),
    (0x0D57, 0x0D57, "VPst"),
    (0x0D5F, 0x0D61, "B"),
    (0x0D62, 0x0D63, "VBlw"),
    (0x0D66, 0x0D6F, "B"),
    (0x0D7A, 0x0D7F, "IND"),
    (0x0D81, 0x0D81, "VMAbv"),
    (0x0D82, 0x0D83, "VMPst"),
    (0x0D85, 0x0DC6, "B"),
    (0x0DCA, 0x0DCA, "H"),
    (0x0DCF, 0x0DD1, "VPst"),
    (0x0DD2, 0x0DD3, "VAbv"),
    (0x0DD4, 0x0DD6, "VBlw"),
    (0x0DD8, 0x0DD8, "VPst"),
    (0x0DD9, 0x0DDE, "VPre"),
    (0x0DDF, 0x0DDF, "VPst"),
    (0x0DE6, 0x0DEF, "B"),
    (0x0DF2, 0x0DF3, "VPst"),
    (0x0F00, 0x0F06, "B"),
    (0x0F18, 0x0F19, "VBlw"),
    (0x0F20, 0x0F33, "B"),
    (0x0F35, 0x0F37, "FBlw"),
    (0x0F39, 0x0F39, "CMAbv"),
    (0x0F3E, 0x0F3E, "VPst"),
    (0x0F3F, 0x0F3F, "VPre"),
    (0x0F40, 0x0F6C, "B"),
    (0x0F71, 0x0F71, "CMBlw"),
    (0x0F72, 0x0F72, "VBlw"),
    (0x0F73, 0x0F74, "VAbv"),
    (0x0F75, 0x0F75, "VBlw"),
    (0x0F76, 0x0F79, "VAbv"),
    (0x0F7A, 0x0F7D, "VBlw"),
    (0x0F7E, 0x0F7E, "VMAbv"),
    (0x0F7F, 0x0F7F, "IND"),
    (0x0F80, 0x0F80, "VBlw"),
    (0x0F81, 0x0F81, "VAbv"),
    (0x0F82, 0x0F83, "VMAbv"),
    (0x0F84, 0x0F84, "VBlw"),
    (0x0F85, 0x0F85, "IND"),
    (0x0F86, 0x0F87, "VMAbv"),
    (0x0F88, 0x0F8C, "B"),
    (0x0F8D, 0x0FBC, "SUB"),
    (0x0FC6, 0x0FC6, "FBlw"),
    (0x1000, 0x102A, "B"),
    (0x102B, 0x102C, "VPst"),
    (0x102D, 0x102E, "VAbv"),
    (0x102F, 0x1030, "VBlw"),
    (0x1031, 0x1031, "VPre"),
    (0x1032, 0x1035, "VAbv"),
    (0x1036, 0x1036, "VMAbv"),
    (0x1037, 0x1037, "VMBlw"),
    (0x1038, 0x1038, "VMPst"),
    (0x1039, 0x1039, "H"),
    (0x103A, 0x103A, "VAbv"),
    (0x103B, 0x103B, "MPst"),
    (0x103C, 0x103C, "MPre"),
    (0x103D, 0x103E, "MBlw"),
    (0x103F, 0x1049, "B"),
    (0x104B, 0x104E, "GB"),
    (0x1050, 0x1055, "B"),
    (0x1056, 0x1057, "VPst"),
    (0x1058, 0x1059, "VBlw"),
    (0x105A, 0x105D, "B"),
    (0x105E, 0x1060, "MBlw"),
    (0x1061, 0x1061, "B"),
    (0x1062, 0x1062, "VPst"),
    (0x1063, 0x1064, "VMPst"),
    (0x1065, 0x1066, "B"),
    (0x1067, 0x1068, "VPst"),
    (0x1069, 0x106D, "VMPst"),
    (0x106E, 0x1070, "B"),
    (0x1071, 0x1074, "VAbv"),
    (0x1075, 0x1081, "B"),
    (0x1082, 0x1082, "MBlw"),
    (0x1083, 0x1083, "VPst"),
    (0x1084, 0x1084, "VPre"),
    (0x1085, 0x1086, "VAbv"),
    (0x1087, 0x108C, "VMPst"),
    (0x108D, 0x108D, "VMBlw"),
    (0x108E, 0x108E, "B"),
    (0x108F, 0x108F, "VMPst"),
    (0x1090, 0x1099, "B"),
    (0x109A, 0x109B, "VMPst"),
    (0x109C, 0x109C, "VPst"),
    (0x109D, 0x109D, "VAbv"),
    (0x1700, 0x1711, "B"),
    (0x1712, 0x1712, "VAbv"),
    (0x1713, 0x1714, "VBlw"),
    (0x1720, 0x1731, "B"),
    (0x1732, 0x1732, "VAbv"),
    (0x1733, 0x1734, "VBlw"),
    (0x1740, 0x1751, "B"),
    (0x1752, 0x1752, "VAbv"),
    (0x1753, 0x1753, "VBlw"),
    (0x1760, 0x1770, "B"),
    (0x1772, 0x1772, "VAbv"),
    (0x1773, 0x1773, "VBlw"),
    (0x1780, 0x17B3, "B"),
    (0x17B6, 0x17B6, "VPst"),
    (0x17B7, 0x17BA, "VAbv"),
    (0x17BB, 0x17BD, "VBlw"),
    (0x17BE, 0x17C5, "VPre"),
    (0x17C6, 0x17C6, "VMAbv"),
    (0x17C7, 0x17C7, "VMPst"),
    (0x17C8, 0x17C8, "VPst"),
    (0x17C9, 0x17CA, "VMAbv"),
    (0x17CB, 0x17CB, "FMAbv"),
    (0x17CC, 0x17CC, "FAbv"),
    (0x17CD, 0x17CD, "CMAbv"),
    (0x17CE, 0x17CE, "FMAbv"),
    (0x17CF, 0x17CF, "VMAbv"),
    (0x17D0, 0x17D0, "FMAbv"),
    (0x17D1, 0x17D1, "VAbv"),
    (0x17D2, 0x17D2, "H"),
    (0x17D3, 0x17D3, "FMAbv"),
    (0x17DC, 0x17DC, "B"),
    (0x17DD, 0x17DD, "FMAbv"),
    (0x17E0, 0x180A, "B"),
    (0x180B, 0x180D, "O"),
    (0x1820, 0x1878, "B"),
    (0x1880, 0x1884, "GB"),
    (0x1885, 0x1886, "CMAbv"),
    (0x1887, 0x18A8, "B"),
    (0x18A9, 0x18A9, "CMBlw"),
    (0x18AA, 0x18AA, "B"),
    (0x1900, 0x1900, "GB"),
    (0x1901, 0x191E, "B"),
    (0x1920, 0x1921, "VAbv"),
    (0x1922, 0x1922, "VBlw"),
    (0x1923, 0x1924, "VPst"),
    (0x1925, 0x1928, "VAbv"),
    (0x1929, 0x192B, "SUB"),
    (0x1930, 0x1931, "FPst"),
    (0x1932, 0x1932, "VMBlw"),
    (0x1933, 0x1938, "FPst"),
    (0x1939, 0x1939, "FBlw"),
    (0x193A, 0x193A, "VMAbv"),
    (0x193B, 0x193B, "FMBlw"),
    (0x1946, 0x19C7, "B"),
    (0x19C8, 0x19C9, "VMPst"),
    (0x19D0, 0x1A16, "B"),
    (0x1A17, 0x1A18, "VAbv"),
    (0x1A19, 0x1A19, "VPre"),
    (0x1A1A, 0x1A1A, "VPst"),
    (0x1A1B, 0x1A1B, "VAbv"),
    (0x1A20, 0x1A54, "B"),
    (0x1A55, 0x1A55, "MPre"),
    (0x1A56, 0x1A56, "MBlw"),
    (0x1A57, 0x1A57, "SUB"),
    (0x1A58, 0x1A59, "FAbv"),
    (0x1A5A, 0x1A5A, "MAbv"),
    (0x1A5B, 0x1A5E, "SUB"),
    (0x1A60, 0x1A60, "Sk"),
    (0x1A61, 0x1A61, "VPst"),
    (0x1A62, 0x1A62, "VAbv"),
    (0x1A63, 0x1A64, "VPst"),
    (0x1A65, 0x1A68, "VAbv"),
    (0x1A69, 0x1A6A, "VBlw"),
    (0x1A6B, 0x1A6B, "VAbv"),
    (0x1A6C, 0x1A6C, "VBlw"),
    (0x1A6D, 0x1A6D, "VPst"),
    (0x1A6E, 0x1A72, "VPre"),
    (0x1A73, 0x1A73, "VAbv"),
    (0x1A74, 0x1A79, "VMAbv"),
    (0x1A7A, 0x1A7A, "VAbv"),
    (0x1A7B, 0x1A7C, "VMAbv"),
    (0x1A7F, 0x1A7F, "VMBlw"),
    (0x1A80, 0x1A99, "B"),
    (0x1B00, 0x1B02, "VMAbv"),
    (0x1B03, 0x1B03, "FAbv"),
    (0x1B04, 0x1B04, "VMPst"),
    (0x1B05, 0x1B33, "B"),
    (0x1B34, 0x1B34, "CMAbv"),
    (0x1B35, 0x1B35, "VPst"),
    (0x1B36, 0x1B37, "VAbv"),
    (0x1B38, 0x1B3B, "VBlw"),
    (0x1B3C, 0x1B3D, "VAbv"),
    (0x1B3E, 0x1B41, "VPre"),
    (0x1B42, 0x1B43, "VAbv"),
    (0x1B44, 0x1B44, "H"),
    (0x1B45, 0x1B59, "B"),
    (0x1B5B, 0x1B5F, "GB"),
    (0x1B61, 0x1B61, "S"),
    (0x1B62, 0x1B62, "GB"),
    (0x1B63, 0x1B67, "S"),
    (0x1B68, 0x1B68, "GB"),
    (0x1B69, 0x1B6A, "S"),
    (0x1B6B, 0x1B6B, "SMAbv"),
    (0x1B6C, 0x1B6C, "SMBlw"),
    (0x1B6D, 0x1B73, "SMAbv"),
    (0x1B80, 0x1B80, "VMAbv"),
    (0x1B81, 0x1B81, "FAbv"),
    (0x1B82, 0x1B82, "VMPst"),
    (0x1B83, 0x1BA0, "B"),
    (0x1BA1, 0x1BA3, "SUB"),
    (0x1BA4, 0x1BA4, "VAbv"),
    (0x1BA5, 0x1BA5, "VBlw"),
    (0x1BA6, 0x1BA6, "VPre"),
    (0x1BA7, 0x1BA7, "VPst"),
    (0x1BA8, 0x1BA9, "VAbv"),
    (0x1BAA, 0x1BAA, "VPst"),
    (0x1BAB, 0x1BAB, "H"),
    (0x1BAC, 0x1BAD, "SUB"),
    (0x1BAE, 0x1BE5, "B"),
    (0x1BE6, 0x1BE6, "CMAbv"),
    (0x1BE7, 0x1BE7, "VPst"),
    (0x1BE8, 0x1BE9, "VAbv"),
    (0x1BEA, 0x1BEC, "VPst"),
    (0x1BED, 0x1BED, "VAbv"),
    (0x1BEE, 0x1BEE, "VPst"),
    (0x1BEF, 0x1BEF, "VAbv"),
    (0x1BF0, 0x1BF1, "FAbv"),
    (0x1BF2, 0x1BF3, "CMBlw"),
    (0x1C00, 0x1C23, "B"),
    (0x1C24, 0x1C25, "SUB"),
    (0x1C26, 0x1C26, "VPst"),
    (0x1C27, 0x1C29, "VPre"),
    (0x1C2A, 0x1C2B, "VPst"),
    (0x1C2C, 0x1C2C, "VBlw"),
    (0x1C2D, 0x1C33, "FAbv"),
    (0x1C34, 0x1C35, "VMPre"),
    (0x1C36, 0x1C36, "FMAbv"),
    (0x1C37, 0x1C37, "CMBlw"),
    (0x1C40, 0x1C4F, "B"),
    (0x1CD0, 0x1CD2, "VMAbv"),
    (0x1CD4, 0x1CD9, "VMBlw"),
    (0x1CDA, 0x1CDB, "VMAbv"),
    (0x1CDC, 0x1CDF, "VMBlw"),
    (0x1CE0, 0x1CE0, "VMAbv"),
    (0x1CE1, 0x1CE1, "VMPst"),
    (0x1CE2, 0x1CED, "VMBlw"),
    (0x1CF2, 0x1CF3, "IND"),
    (0x1CF4, 0x1CF4, "VMAbv"),
    (0x1CF5, 0x1CF6, "CS"),
    (0x1CF7, 0x1CF7, "VMPst"),
    (0x1CF8, 0x1CF9, "VMAbv"),
    (0x1CFA, 0x1CFA, "GB"),
    (0x1DFB, 0x1DFB, "FMAbv"),
    (0x200C, 0x200C, "ZWNJ"),
    (0x200D, 0x200D, "ZWJ"),
    (0x2010, 0x2014, "GB"),
    (0x2060, 0x2060, "WJ"),
    (0x2074, 0x2084, "FMPst"),
    (0x20F0, 0x20F0, "VMAbv"),
    (0x25CC, 0x2D6F, "B"),
    (0x2D7F, 0x2D7F, "H"),
    (0xA800, 0xA801, "B"),
    (0xA802, 0xA802, "VAbv"),
    (0xA803, 0xA805, "B"),
    (0xA806, 0xA806, "H"),
    (0xA807, 0xA80A, "B"),
    (0xA80B, 0xA80B, "VMAbv"),
    (0xA80C, 0xA822, "B"),
    (0xA823, 0xA824, "VPst"),
    (0xA825, 0xA825, "VBlw"),
    (0xA826, 0xA826, "VAbv"),
    (0xA827, 0xA827, "VPst"),
    (0xA82C, 0xA82C, "VBlw"),
    (0xA840, 0xA873, "B"),
    (0xA880, 0xA881, "VMPst"),
    (0xA882, 0xA8B3, "B"),
    (0xA8B4, 0xA8B4, "MPst"),
    (0xA8B5, 0xA8C3, "VPst"),
    (0xA8C4, 0xA8C4, "H"),
    (0xA8C5, 0xA8C5, "VMAbv"),
    (0xA8D0, 0xA8D9, "B"),
    (0xA8E0, 0xA8F1, "VMAbv"),
    (0xA8F2, 0xA8FE, "B"),
    (0xA8FF, 0xA8FF, "VAbv"),
    (0xA900, 0xA925, "B"),
    (0xA926, 0xA92A, "VAbv"),
    (0xA92B, 0xA92D, "VMBlw"),
    (0xA930, 0xA946, "B"),
    (0xA947, 0xA949, "VBlw"),
    (0xA94A, 0xA94A, "VAbv"),
    (0xA94B, 0xA94E, "VBlw"),
    (0xA94F, 0xA951, "FAbv"),
    (0xA952, 0xA952, "FPst"),
    (0xA953, 0xA953, "VPst"),
    (0xA980, 0xA981, "VMAbv"),
    (0xA982, 0xA982, "FAbv"),
    (0xA983, 0xA983, "VMPst"),
    (0xA984, 0xA9B2, "B"),
    (0xA9B3, 0xA9B3, "CMAbv"),
    (0xA9B4, 0xA9B5, "VPst"),
    (0xA9B6, 0xA9B7, "VAbv"),
    (0xA9B8, 0xA9B9, "VBlw"),
    (0xA9BA, 0xA9BB, "VPre"),
    (0xA9BC, 0xA9BC, "VAbv"),
    (0xA9BD, 0xA9BD, "MBlw"),
    (0xA9BE, 0xA9BE, "MPst"),
    (0xA9BF, 0xA9BF, "MBlw"),
    (0xA9C0, 0xA9C0, "H"),
    (0xA9D0, 0xA9E4, "B"),
    (0xA9E5, 0xA9E5, "VAbv"),
    (0xA9E7, 0xAA28, "B"),
    (0xAA29, 0xAA29, "VMAbv"),
    (0xAA2A, 0xAA2C, "VAbv"),
    (0xAA2D, 0xAA2D, "VBlw"),
    (0xAA2E, 0xAA2E, "VAbv"),
    (0xAA2F, 0xAA30, "VPre"),
    (0xAA31, 0xAA31, "VAbv"),
    (0xAA32, 0xAA32, "VBlw"),
    (0xAA33, 0xAA33, "MPst"),
    (0xAA34, 0xAA34, "MPre"),
    (0xAA35, 0xAA35, "MAbv"),
    (0xAA36, 0xAA36, "MBlw"),
    (0xAA40, 0xAA42, "B"),
    (0xAA43, 0xAA43, "FAbv"),
    (0xAA44, 0xAA4B, "B"),
    (0xAA4C, 0xAA4C, "FAbv"),
    (0xAA4D, 0xAA4D, "FPst"),
    (0xAA50, 0xAA73, "B"),
    (0xAA74, 0xAA76, "GB"),
    (0xAA7A, 0xAA7A, "B"),
    (0xAA7B, 0xAA7B, "VMPst"),
    (0xAA7C, 0xAA7C, "VMAbv"),
    (0xAA7D, 0xAA7D, "VMPst"),
    (0xAA7E, 0xAAAF, "B"),
    (0xAAB0, 0xAAB0, "VAbv"),
    (0xAAB1, 0xAAB1, "B"),
    (0xAAB2, 0xAAB3, "VAbv"),
    (0xAAB4, 0xAAB4, "VBlw"),
    (0xAAB5, 0xAAB6, "B"),
    (0xAAB7, 0xAAB8, "VAbv"),
    (0xAAB9, 0xAABD, "B"),
    (0xAABE, 0xAABE, "VAbv"),
    (0xAABF, 0xAABF, "VMAbv"),
    (0xAAC0, 0xAAC0, "B"),
    (0xAAC1, 0xAAC1, "VMAbv"),
    (0xAAC2, 0xAAEA, "B"),
    (0xAAEB, 0xAAEB, "VPre"),
    (0xAAEC, 0xAAEC, "VBlw"),
    (0xAAED, 0xAAED, "VAbv"),
    (0xAAEE, 0xAAEE, "VPre"),
    (0xAAEF, 0xAAEF, "VPst"),
    (0xAAF5, 0xAAF5, "VMPst"),
    (0xAAF6, 0xAAF6, "H"),
    (0xABC0, 0xABE2, "B"),
    (0xABE3, 0xABE4, "VPst"),
    (0xABE5, 0xABE5, "VAbv"),
    (0xABE6, 0xABE7, "VPst"),
    (0xABE8, 0xABE8, "VBlw"),
    (0xABE9, 0xABEA, "VPst"),
    (0xABEC, 0xABEC, "VMPst"),
    (0xABED, 0xABED, "VBlw"),
    (0xABF0, 0x10A00, "B"),
    (0x10A01, 0x10A03, "VBlw"),
    (0x10A05, 0x10A05, "VAbv"),
    (0x10A06, 0x10A06, "VBlw"),
    (0x10A0C, 0x10A0C, "VPst"),
    (0x10A0D, 0x10A0E, "VMBlw"),
    (0x10A0F, 0x10A0F, "VMAbv"),
    (0x10A10, 0x10A35, "B"),
    (0x10A38, 0x10A38, "CMAbv"),
    (0x10A39, 0x10A3A, "CMBlw"),
    (0x10A3F, 0x10A3F, "H"),
    (0x10A40, 0x10AE4, "B"),
    (0x10AE5, 0x10AE6, "CMBlw"),
    (0x10B80, 0x10D23, "B"),
    (0x10D24, 0x10D26, "VMAbv"),
    (0x10D27, 0x10D27, "CMAbv"),
    (0x10D30, 0x10EA9, "B"),
    (0x10EAB, 0x10EAC, "VAbv"),
    (0x10EB0, 0x10F45, "B"),
    (0x10F46, 0x10F50, "VMBlw"),
    (0x10F51, 0x10FCB, "B"),
    (0x11000, 0x11000, "VMPst"),
    (0x11001, 0x11001, "VMAbv"),
    (0x11002, 0x11002, "VMPst"),
    (0x11003, 0x11004, "CS"),
    (0x11005, 0x11037, "B"),
    (0x11038, 0x1103B, "VAbv"),
    (0x1103C, 0x11041, "VBlw"),
    (0x11042, 0x11045, "VAbv"),
    (0x11046, 0x11046, "HVM"),
    (0x11052, 0x11065, "N"),
    (0x11066, 0x1106F, "B"),
    (0x1107F, 0x1107F, "HN"),
    (0x11080, 0x11081, "VMAbv"),
    (0x11082, 0x11082, "VMPst"),
    (0x11083, 0x110AF, "B"),
    (0x110B0, 0x110B0, "VPst"),
    (0x110B1, 0x110B1, "VPre"),
    (0x110B2, 0x110B2, "VPst"),
    (0x110B3, 0x110B4, "VBlw"),
    (0x110B5, 0x110B6, "VAbv"),
    (0x110B7, 0x110B8, "VPst"),
    (0x110B9, 0x110B9, "H"),
    (0x110BA, 0x110BA, "CMBlw"),
    (0x11100, 0x11102, "VMAbv"),
    (0x11103, 0x11126, "B"),
    (0x11127, 0x11129, "VBlw"),
    (0x1112A, 0x1112B, "VAbv"),
    (0x1112C, 0x1112C, "VPre"),
    (0x1112D, 0x1112D, "VBlw"),
    (0x1112E, 0x1112F, "VAbv"),
    (0x11130, 0x11130, "VBlw"),
    (0x11131, 0x11132, "VAbv"),
    (0x11133, 0x11133, "H"),
    (0x11134, 0x11134, "CMAbv"),
    (0x11136, 0x11144, "B"),
    (0x11145, 0x11146, "VPst"),
    (0x11147, 0x11172, "B"),
    (0x11173, 0x11173, "CMBlw"),
    (0x11180, 0x11181, "VMAbv"),
    (0x11182, 0x11182, "VMPst"),
    (0x11183, 0x111B2, "B"),
    (0x111B3, 0x111B3, "VPst"),
    (0x111B4, 0x111B4, "VPre"),
    (0x111B5, 0x111B5, "VPst"),
    (0x111B6, 0x111BB, "VBlw"),
    (0x111BC, 0x111BF, "VAbv"),
    (0x111C0, 0x111C0, "H"),
    (0x111C1, 0x111C1, "B"),
    (0x111C2, 0x111C3, "R"),
    (0x111C8, 0x111C8, "GB"),
    (0x111C9, 0x111C9, "FMBlw"),
    (0x111CA, 0x111CA, "CMBlw"),
    (0x111CB, 0x111CB, "VAbv"),
    (0x111CC, 0x111CC, "VBlw"),
    (0x111CE, 0x111CE, "VPre"),
    (0x111CF, 0x111CF, "VMAbv"),
    (0x111D0, 0x1122B, "B"),
    (0x1122C, 0x1122E, "VPst"),
    (0x1122F, 0x1122F, "VBlw"),
    (0x11230, 0x11233, "VAbv"),
    (0x11234, 0x11234, "VMAbv"),
    (0x11235, 0x11235, "H"),
    (0x11236, 0x11237, "CMAbv"),
    (0x1123E, 0x1123E, "VMAbv"),
    (0x11280, 0x112DE, "B"),
    (0x112DF, 0x112DF, "VMAbv"),
    (0x112E0, 0x112E0, "VPst"),
    (0x112E1, 0x112E1, "VPre"),
    (0x112E2, 0x112E2, "VPst"),
    (0x112E3, 0x112E4, "VBlw"),
    (0x112E5, 0x112E8, "VAbv"),
    (0x112E9, 0x112E9, "CMBlw"),
    (0x112EA, 0x112EA, "VBlw"),
    (0x112F0, 0x112F9, "B"),
    (0x11300, 0x11303, "VMAbv"),
    (0x11305, 0x11339, "B"),
    (0x1133B, 0x1133C, "CMBlw"),
    (0x1133D, 0x1133D, "B"),
    (0x1133E, 0x1133F, "VPst"),
    (0x11340, 0x11340, "VAbv"),
    (0x11341, 0x11344, "VPst"),
    (0x11347, 0x1134C, "VPre"),
    (0x1134D, 0x1134D, "HVM"),
    (0x11357, 0x11357, "VPst"),
    (0x1135E, 0x11361, "B"),
    (0x11362, 0x11363, "VPst"),
    (0x11366, 0x11374, "VMAbv"),
    (0x11400, 0x11434, "B"),
    (0x11435, 0x11435, "VPst"),
    (0x11436, 0x11436, "VPre"),
    (0x11437, 0x11437, "VPst"),
    (0x11438, 0x1143D, "VBlw"),
    (0x1143E, 0x1143F, "VAbv"),
    (0x11440, 0x11441, "VPst"),
    (0x11442, 0x11442, "H"),
    (0x11443, 0x11444, "VMAbv"),
    (0x11445, 0x11445, "VMPst"),
    (0x11446, 0x11446, "CMBlw"),
    (0x11447, 0x11459, "B"),
    (0x1145E, 0x1145E, "FMAbv"),
    (0x1145F, 0x1145F, "B"),
    (0x11460, 0x11461, "CS"),
    (0x11481, 0x114AF, "B"),
    (0x114B0, 0x114B0, "VPst"),
    (0x114B1, 0x114B1, "VPre"),
    (0x114B2, 0x114B2, "VPst"),
    (0x114B3, 0x114B8, "VBlw"),
    (0x114B9, 0x114B9, "VPre"),
    (0x114BA, 0x114BA, "VAbv"),
    (0x114BB, 0x114BC, "VPre"),
    (0x114BD, 0x114BD, "VPst"),
    (0x114BE, 0x114BE, "VPre"),
    (0x114BF, 0x114C1, "VMAbv"),
    (0x114C2, 0x114C2, "H"),
    (0x114C3, 0x114C3, "CMBlw"),
    (0x114C4, 0x115AE, "B"),
    (0x115AF, 0x115AF, "VPst"),
    (0x115B0, 0x115B0, "VPre"),
    (0x115B1, 0x115B1, "VPst"),
    (0x115B2, 0x115B5, "VBlw"),
    (0x115B8, 0x115BB, "VPre"),
    (0x115BC, 0x115BD, "VMAbv"),
    (0x115BE, 0x115BE, "VMPst"),
    (0x115BF, 0x115BF, "H"),
    (0x115C0, 0x115C0, "CMBlw"),
    (0x115D8, 0x115DB, "B"),
    (0x115DC, 0x115DD, "VBlw"),
    (0x11600, 0x1162F, "B"),
    (0x11630, 0x11632, "VPst"),
    (0x11633, 0x11638, "VBlw"),
    (0x11639, 0x1163A, "VAbv"),
    (0x1163B, 0x1163C, "VPst"),
    (0x1163D, 0x1163D, "VMAbv"),
    (0x1163E, 0x1163E, "VMPst"),
    (0x1163F, 0x1163F, "H"),
    (0x11640, 0x11640, "VAbv"),
    (0x11650, 0x116AA, "B"),
    (0x116AB, 0x116AB, "VMAbv"),
    (0x116AC, 0x116AC, "VMPst"),
    (0x116AD, 0x116AD, "VAbv"),
    (0x116AE, 0x116AE, "VPre"),
    (0x116AF, 0x116AF, "VPst"),
    (0x116B0, 0x116B1, "VBlw"),
    (0x116B2, 0x116B5, "VAbv"),
    (0x116B6, 0x116B6, "H"),
    (0x116B7, 0x116B7, "CMBlw"),
    (0x116B8, 0x1171A, "B"),
    (0x1171D, 0x1171D, "MBlw"),
    (0x1171E, 0x1171E, "MPre"),
    (0x1171F, 0x1171F, "MAbv"),
    (0x11720, 0x11721, "VPst"),
    (0x11722, 0x11723, "VAbv"),
    (0x11724, 0x11725, "VBlw"),
    (0x11726, 0x11726, "VPre"),
    (0x11727, 0x11727, "VAbv"),
    (0x11728, 0x11728, "VBlw"),
    (0x11729, 0x1172A, "VAbv"),
    (0x1172B, 0x1172B, "VMAbv"),
    (0x11730, 0x1182B, "B"),
    (0x1182C, 0x1182C, "VPst"),
    (0x1182D, 0x1182D, "VPre"),
    (0x1182E, 0x1182E, "VPst"),
    (0x1182F, 0x11832, "VBlw"),
    (0x11833, 0x11836, "VAbv"),
    (0x11837, 0x11837, "VMAbv"),
    (0x11838, 0x11838, "VMPst"),
    (0x11839, 0x11839, "H"),
    (0x1183A, 0x1183A, "CMBlw"),
    (0x11900, 0x1192F, "B"),
    (0x11930, 0x11934, "VPst"),
    (0x11935, 0x11938, "VPre"),
    (0x1193B, 0x1193C, "VMAbv"),
    (0x1193D, 0x1193D, "VPst"),
    (0x1193E, 0x1193E, "H"),
    (0x1193F, 0x1193F, "R"),
    (0x11940, 0x11940, "MPst"),
    (0x11941, 0x11941, "R"),
    (0x11942, 0x11942, "MPst"),
    (0x11943, 0x11943, "CMBlw"),
    (0x11950, 0x119D0, "B"),
    (0x119D1, 0x119D1, "VPst"),
    (0x119D2, 0x119D2, "VPre"),
    (0x119D3, 0x119D3, "VPst"),
    (0x119D4, 0x119D7, "VBlw"),
    (0x119DA, 0x119DB, "VAbv"),
    (0x119DC, 0x119DD, "VPst"),
    (0x119DE, 0x119DF, "VMPst"),
    (0x119E0, 0x119E0, "H"),
    (0x119E1, 0x119E1, "B"),
    (0x119E4, 0x119E4, "VPre"),
    (0x11A00, 0x11A00, "B"),
    (0x11A01, 0x11A01, "VAbv"),
    (0x11A02, 0x11A03, "VBlw"),
    (0x11A04, 0x11A09, "VAbv"),
    (0x11A0A, 0x11A0A, "VBlw"),
    (0x11A0B, 0x11A32, "B"),
    (0x11A33, 0x11A33, "FMBlw"),
    (0x11A34, 0x11A34, "VBlw"),
    (0x11A35, 0x11A38, "VMAbv"),
    (0x11A39, 0x11A39, "VMPst"),
    (0x11A3A, 0x11A3A, "R"),
    (0x11A3B, 0x11A3E, "MBlw"),
    (0x11A3F, 0x11A45, "GB"),
    (0x11A47, 0x11A47, "H"),
    (0x11A50, 0x11A50, "B"),
    (0x11A51, 0x11A51, "VAbv"),
    (0x11A52, 0x11A53, "VBlw"),
    (0x11A54, 0x11A56, "VAbv"),
    (0x11A57, 0x11A58, "VPst"),
    (0x11A59, 0x11A5B, "VBlw"),
    (0x11A5C, 0x11A83, "B"),
    (0x11A84, 0x11A89, "R"),
    (0x11A8A, 0x11A95, "FBlw"),
    (0x11A96, 0x11A96, "VMAbv"),
    (0x11A97, 0x11A97, "VMPst"),
    (0x11A98, 0x11A98, "CMAbv"),
    (0x11A99, 0x11A99, "H"),
    (0x11A9D, 0x11C2E, "B"),
    (0x11C2F, 0x11C2F, "VPst"),
    (0x11C30, 0x11C31, "VAbv"),
    (0x11C32, 0x11C36, "VBlw"),
    (0x11C38, 0x11C3B, "VAbv"),
    (0x11C3C, 0x11C3D, "VMAbv"),
    (0x11C3E, 0x11C3E, "VMPst"),
    (0x11C3F, 0x11C3F, "H"),
    (0x11C40, 0x11C40, "B"),
    (0x11C44, 0x11C45, "GB"),
    (0x11C50, 0x11C8F, "B"),
    (0x11C92, 0x11CAF, "SUB"),
    (0x11CB0, 0x11CB0, "VBlw"),
    (0x11CB1, 0x11CB1, "VPre"),
    (0x11CB2, 0x11CB2, "VBlw"),
    (0x11CB3, 0x11CB3, "VAbv"),
    (0x11CB4, 0x11CB4, "VPst"),
    (0x11CB5, 0x11CB6, "VMAbv"),
    (0x11D00, 0x11D30, "B"),
    (0x11D31, 0x11D35, "VAbv"),
    (0x11D36, 0x11D36, "VBlw"),
    (0x11D3A, 0x11D3F, "VAbv"),
    (0x11D40, 0x11D41, "VMAbv"),
    (0x11D42, 0x11D42, "CMBlw"),
    (0x11D43, 0x11D43, "VAbv"),
    (0x11D44, 0x11D44, "VBlw"),
    (0x11D45, 0x11D45, "H"),
    (0x11D46, 0x11D46, "R"),
    (0x11D47, 0x11D47, "MBlw"),
    (0x11D50, 0x11D89, "B"),
    (0x11D8A, 0x11D8E, "VPst"),
    (0x11D90, 0x11D91, "VAbv"),
    (0x11D93, 0x11D94, "VPst"),
    (0x11D95, 0x11D95, "VMAbv"),
    (0x11D96, 0x11D96, "VMPst"),
    (0x11D97, 0x11D97, "H"),
    (0x11DA0, 0x11EF1, "B"),
    (0x11EF2, 0x11EF2, "GB"),
    (0x11EF3, 0x11EF3, "VAbv"),
    (0x11EF4, 0x11EF4, "VBlw"),
    (0x11EF5, 0x11EF5, "VPre"),
    (0x11EF6, 0x11EF6, "VPst"),
    (0x13430, 0x13436, "H"),
    (0x16B00, 0x16B2F, "B"),
    (0x16B30, 0x16B36, "VMAbv"),
    (0x16F00, 0x16F4A, "B"),
    (0x16F4F, 0x16F4F, "CMBlw"),
    (0x16F50, 0x16F50, "IND"),
    (0x16F51, 0x16F87, "VBlw"),
    (0x16F8F, 0x16F92, "VMBlw"),
    (0x16FE4, 0x1BC99, "B"),
    (0x1BC9D, 0x1BC9E, "CMBlw"),
    (0x1E100, 0x1E12C, "B"),
    (0x1E130, 0x1E136, "VMAbv"),
    (0x1E137, 0x1E2EB, "B"),
    (0x1E2EC, 0x1E2EF, "VMAbv"),
    (0x1E2F0, 0x1E943, "B"),
    (0x1E944, 0x1E94A, "CMAbv"),
    (0x1E94B, 0x1E959, "B"),
)
