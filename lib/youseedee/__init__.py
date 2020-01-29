import zipfile
from os.path import expanduser
import os
import requests
import sys
import re
import csv

UCD_URL = "https://unicode.org/Public/UCD/latest/ucd/UCD.zip"

def ucd_dir():
  ucddir = os.path.expanduser("~/.youseedee")
  if not os.path.isdir(ucddir):
    os.mkdir(ucddir)
  return ucddir

def ensure_files():
  if os.path.isfile(os.path.join(ucd_dir(), "UnicodeData.txt")):
    return

  zip_path = os.path.join(ucd_dir(), "UCD.zip")
  if not os.path.isfile(zip_path):
    with open(zip_path, "wb") as f:
      print("Downloading Unicode Character Database...")
      response = requests.get(UCD_URL, stream=True)
      total_length = response.headers.get('content-length')

      if total_length is None: # no content length header
        f.write(response.content)
      else:
        dl = 0
        total_length = int(total_length)
        for data in response.iter_content(chunk_size=4096):
          dl += len(data)
          f.write(data)
          done = int(50 * dl / total_length)
          sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50-done)) )
          sys.stdout.flush()

  with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(ucd_dir())

def parse_file_ranges(filename):
  ensure_files()
  ranges = []
  with open(os.path.join(ucd_dir(), filename), "r") as f:
    for line in f:
      if re.match("^\s*#", line): continue
      if re.match("^\s*$", line): continue
      line = re.sub("#.*","",line)
      matches = re.match("^([0-9A-F]{4,})(?:\.\.([0-9A-F]{4,}))?\s*;\s*([^;]+?)\s*$", line)
      start, end, content = matches.groups()
      if end is None: end = start
      ranges.append(( int(start,16), int(end,16),content))
  return ranges

def parse_file_semicolonsep(filename):
  ensure_files()
  data = {}
  with open(os.path.join(ucd_dir(), filename), "r", newline='') as f:
    reader = csv.reader(f, delimiter=';',skipinitialspace=True)
    for row in reader:
      if len(row) < 2: continue
      if re.match("^#",row[0]): continue
      row[-1] = re.sub("\s*#.*","",row[-1])
      row[0] = int(row[0],16)
      data[row[0]] = row[1:]
  return data

def dictget(filename, codepoint):
  fileentry = database[filename]
  if not "data" in fileentry:
    fileentry["data"] = fileentry["reader"](filename)
  if not codepoint in fileentry["data"]:
    return {}
  d = fileentry["data"][codepoint]
  r = {}
  for ix, p in enumerate(database[filename]["properties"]):
    if p == "IGNORE": continue
    r[p] = d[ix]
  return r

def rangereader(filename, codepoint):
  fileentry = database[filename]
  if not "data" in fileentry:
    fileentry["data"] = fileentry["reader"](filename)
  for rangerow in fileentry["data"]:
    start, end = rangerow[0],rangerow[1]
    if codepoint >= start and codepoint <= end:
      data = rangerow[2:]
      r = {}
      for ix, p in enumerate(database[filename]["properties"]):
        if p == "IGNORE": continue
        r[p] = data[ix]
      return r
  return {}

database = {
  "ArabicShaping.txt": {
    "properties": [ "IGNORE", "Joining_Type", "Joining_Group" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "BidiBrackets.txt": {
    "properties": [ "Bidi_Paired_Bracket", "Bidi_Paired_Bracket_Type" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "BidiMirroring.txt": {
    "properties": [ "Bidi_Mirroring_Glyph" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "Blocks.txt": {
    "properties": [ "Block" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "CaseFolding.txt": {
    "properties": [ "Case_Folding_Status", "Case_Folding_Mapping" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "DerivedAge.txt": {
    "properties": [ "Age" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "EastAsianWidth.txt": {
    "properties": [ "East_Asian_Width" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "HangulSyllableType.txt": {
    "properties": [ "Hangul_Syllable_Type" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "IndicPositionalCategory.txt": {
    "properties": [ "Indic_Positional_Category" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "IndicSyllabicCategory.txt": {
    "properties": [ "Indic_Syllabic_Category" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "Jamo.txt": {
    "properties": [ "Jamo_Short_Name" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "LineBreak.txt": {
    "properties": [ "Line_Break" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "NameAliases.txt": {
    "properties": [ "Name_Alias" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "Scripts.txt": {
    "properties": [ "Script" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "ScriptExtensions.txt": {
    "properties": [ "Script_Extensions" ],
    "reader": parse_file_ranges, "datareader": rangereader
  },
  "SpecialCasing.txt": {
    "properties": [ "Uppercase_Mapping", "Lowercase_Mapping", "Titlecase_Mapping" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "UnicodeData.txt": {
    "properties": [ "Name", "General_Category", "Canonical_Combining_Class" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
  "USECategory.txt": {
    "properties": [ "USE_Category" ],
    "reader": parse_file_semicolonsep, "datareader": dictget
  },
}

def ucd_data(codepoint):
  out = {}
  for file, props in database.items():
    out.update(props["datareader"](file, codepoint))
  return out