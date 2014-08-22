librarian
=========

Ebook manager that can sync to a Kindle Paperwhite and automatically create collections.

There is no guarantee that this will be useful to anyone but myself.

what it does
------------

This is made of two parts:

- *librarian.py*, which can import ebooks, rename them from metadata, convert them to mobi, and sync with a Kindle Paperwhite.
- *Librarian Sync*, which is run on the Kindle, to build automatically the collections created with librarian.py.

*librarian.py *uses several special folders, as specified in the configuration file:

- *library_root*: where all ebooks are kept. More specifically, it will be divided in subfolders:
    - **import**: temporary place to dump ebooks before they are imported into the library proper
    - **imported**: when an ebook is imported (and renamed), a copy of the original is optionnally placed here.
    - **kindle**: a mirror of the library, with all epubs converted into mobis. This is what will be synced with the Kindle.
    - **library**: where all imported ebooks are safely kept.
- *kindle_root*: where the Kindle is mounted when it is connected by USB. This may depend on your Linux distribution.
- *scrape_root*: if you have ebooks lying around on a drive at random, for example, scraping it will copy them all into the import subfolder.


librarian
---------

### Requirements

- Python 3
- Calibre (librarian.py relies on ebook-meta and ebook-convert, which are part of Calibre)
- pyyaml for python 3

### Configuration

*librarian.py* uses a file, library.yaml, for both configuration and ebook database.

To begin, a minimal example configuration would be:

    General:
        author_aliases:
            Alexandre Dumas Père: Alexandre Dumas
            China Mieville: China Miéville
            Richard Morgan: Richard K. Morgan
        backup_imported_ebooks: true
        kindle_root: /run/media/login/Kindle
        library_root: /home/login/ebooks
        scrape_root: /home/login/documents

After ebooks are imported, each will have an entry (as a YAML document), such as:

    Alexandre Dumas/Alexandre Dumas (1844) Les Trois Mousquetaires.epub:
        author: Alexandre Dumas
        converted_to_mobi_from_hash: faaf34fa7753bee6722fe75066857266a32d1116
        converted_to_mobi_hash: e6278980d4fb66c9c05c4edebdcdc57f37a4dbf8
        date: 1844
        format: epub
        last_synced_hash: e6278980d4fb66c9c05c4edebdcdc57f37a4dbf8
        path: /home/login/ebooks/library/Alexandre Dumas/Alexandre
            Dumas (2004) Les Trois Mousquetaires.epub
        tags: gutenberg,french,already read
        title: Les Trois Mousquetaires

Only the "tags" section should be edited manually, and is originally blank after import. Each tag will
be transformed into a Kindle collection by Librarian Sync.

### Usage

Launch with python3, with the (non-exclusive) options:

- **s**: scrape directory
- **i**: import ebooks
- **r**: refresh database
- **k**: sync with Kindle

*python librarian.py irks* will do all of the above.

While syncing with Kindle, *librarian.py* will keep track of previous conversions to the mobi format (for epub ebooks), 
and of previously synced ebooks on the Kindle, and will try to work no more than necessary.

Note that if books are imported successfully, a refresh is automatically added.
Also, only .epubs and .mobis are imported/scraped, with a preference for .epub when both formats are available.

librarian sync
--------------

This is the part that generates the Kindle collections from a json file.
It can be used completely independantly of librarian.py, provided the collections.json file is correct and in the correct location ( inside the extensions/ folder on the Kindle).

### Requirements

- [A jailbroken Kindle Paperwhite2](http://www.mobileread.com/forums/showthread.php?t=186645)
- [Mobiread Kindlet Kit installed](http://www.mobileread.com/forums/showthread.php?t=233932)
- [KUAL installed](http://www.mobileread.com/forums/showthread.php?t=203326)
- [Python installed](http://www.mobileread.com/forums/showthread.php?t=195474)

For instructions on how to do that, try the [mobiread forum](http://www.mobileread.com/forums/forumdisplay.php?f=150) in general.

This script is inspired by [this thread](http://www.mobileread.com/forums/showthread.php?t=160855).


### Installation

Once the requirements are met, just copy the librariansync folder into the extensions/ folder on the kindle.

### Usage


From the Kindle, launch KUAL. A new menu option "Librarian Sync" should appear.

### What it does


After syncing with the main script librarian.py, and if tags are defined in library.yaml for entries,
the extensions/ folder on the Kindle should contain a file, collections.json.
Librarian Sync removes all collections, then adds the collections as defined in collections.json.
Allow for a few seconds for the Kindle database and interface to reflect the changes made.

### collections.json example

For each path of an ebook (relative to the documents/ folder) is associated a list of collection names.

    {
        "library/Alexandre Dumas/Alexandre Dumas (2004) Les Trois Mousquetaires.mobi": ["gutenberg","french","already read"],
        "library/Alexandre Dumas/Alexandre Dumas (2004) Vingt Ans Après.mobi": ["gutenberg","french","not read yet"],
        "library/Alexandre Dumas/Alexandre Dumas (2011) Le Comte De Monte-Cristo.mobi": ["gutenberg","french","already read"]
    }

Library Sync creates all of the collections mentionned, then associates the relevant ebooks to them.
