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

*librarian.py* uses a configuration file, librarian.yaml.

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

Imported ebooks are kept in a Python dictionary saved and loaded with the marshal module, in library.db.
Until proven otherwise, it seems quick enough.

### Usage

Launch with python3, with the (non-exclusive) options:

- **s**: scrape directory
- **i**: import ebooks
- **r**: refresh database
- **k**: sync with Kindle
- **f** *STRING*: filter and display ebooks containing *STRING* in either its author's name or its title.
- **ft** *STRING* *STRING*: same as **f** but tags the result as the second *STRING*.
- **fd** *STRING *STRING*: same as **f** but removes the result from the tag of the second *STRING*.
- **u** *[STRING]*: filter and display ebooks containing *STRING* among its tags. If *STRING* is omitted, displays all ebooks yet untagged.

*python librarian.py irks* will scrape all ebooks, import them, refresh the database then sync everything to the Kindle.

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

For instructions on how to do that, try the [mobileread forum](http://www.mobileread.com/forums/forumdisplay.php?f=150) in general.

This script is inspired by [this thread](http://www.mobileread.com/forums/showthread.php?t=160855).


### Installation

Once the requirements are met, just copy the librariansync folder into the extensions/ folder on the kindle.

### Usage

From the Kindle, launch KUAL. A new menu option *Librarian Sync* should appear, which contains two entries:

- *Rebuild all collections* : to clear all existing collections and rebuild them using the json file
- *Add to collections* : to only add ebooks to existing or new collections

### What it does

After syncing with the main script librarian.py, and if tags are defined in library.yaml for entries,
the extensions/ folder on the Kindle should contain a file, collections.json.
When *rebuilding collections*, Librarian Sync removes all collections, then adds the collections as defined in collections.json.
When *adding to them*, it preserves already existing collections, and only either add entries to them or creates new collections.
Allow for a few seconds for the Kindle database and interface to reflect the changes made.

### collections.json example

For each path of an ebook (relative to the documents/ folder) is associated a list of collection names.

    {
        "library/Alexandre Dumas/Alexandre Dumas (2004) Les Trois Mousquetaires.mobi": ["gutenberg","french","already read"],
        "library/Alexandre Dumas/Alexandre Dumas (2004) Vingt Ans Après.mobi": ["gutenberg","french","not read yet"],
        "library/Alexandre Dumas/Alexandre Dumas (2011) Le Comte De Monte-Cristo.mobi": ["gutenberg","french","already read"]
    }

Library Sync creates all of the collections mentionned, then associates the relevant ebooks to them.
