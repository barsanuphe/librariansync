#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script can generate a collections.json file compatible with LibrarianSync.
It detects the folder structure relative to the path given as argument, and
associates to any supported ebook a collection named after this relative
path.
"""

import os
import json
import codecs
import sys

SUPPORTED_EXTENSIONS = [".azw",
                        ".mobi",
                        ".prc",
                        ".pobi",
                        ".azw3",
                        ".azw6",
                        ".yj",
                        ".azw1",
                        ".tpz",
                        ".pdf",
                        ".txt",
                        ".html",
                        ".htm",
                        ".jpg",
                        ".jpeg",
                        ".azw2",
                        ".kfx"]


def list_folder_contents():
    folder_contents = {}
    for root, dirs, files in os.walk(EBOOKS_ROOT):
        for f in [get_relative_path(os.path.join(root, el))
                  for el in files
                  if os.path.splitext(el.lower())[1] in SUPPORTED_EXTENSIONS]:
            if get_relative_path(root) != u"":
                folder_contents[f] = [get_relative_path(root)]
    return folder_contents


def get_relative_path(path):
    return path.split(EBOOKS_ROOT)[1]


if __name__ == "__main__":
    try:
        assert len(sys.argv) == 2
        EBOOKS_ROOT = sys.argv[1]
        assert os.path.exists(EBOOKS_ROOT)
    except:
        print("Script must have a valid folder as argument.")
    else:
        js = json.dumps(list_folder_contents(), sort_keys=True, indent=2,
                        separators=(',', ': '), ensure_ascii=False)

        with codecs.open("collections.json", "w", "utf8") as export_json:
            export_json.write(js)
