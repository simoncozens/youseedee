import os
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from youseedee import ucd_data

def test_concurrent_download(tmp_path):
    """Download the ZIP twice at the same time and make sure it doesn't crash.
    """
    # Fake user home dir (where youseedee writes its files)
    os.environ['HOME'] = str(tmp_path)
    os.environ['USERPROFILE'] = str(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_1 = executor.submit(ucd_data, ord('a'))
        sleep(0.1)
        future_2 = executor.submit(ucd_data, ord('a'))
        assert future_1.result() == future_2.result()
