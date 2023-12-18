import os
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from youseedee import ucd_data, parsed_unicode_file

def test_age():
    agedata = parsed_unicode_file("DerivedAge.txt")
    assert "Age" in ucd_data(0x500)
    assert ucd_data(0x500)["Age"] == "3.2"
