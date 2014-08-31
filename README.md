librarian
=========

Ebook manager that can sync to a Kindle Paperwhite and automatically create
collections from tags.

*There is no guarantee that this will be useful to anyone but myself.*

what it does
------------

This is made of two parts:

- *librarian.py*:
    which can import ebooks, rename them from metadata, convert them to mobi,
    and sync with a Kindle Paperwhite.
    It can also perform basic search and add and remove tags.

- *Librarian Sync*:
    runs on the Kindle, and can automatically build the collections based on the
    tags added with librarian.py.

librarian
---------

### Requirements

- Python 3
- Calibre (librarian.py relies on ebook-convert, which are part of Calibre)
- pyyaml for python 3

### Configuration

*librarian.py *uses several special folders, as specified in the configuration
file *librarian.yaml*:

- *library_root*: where all ebooks are kept. More specifically, it will be divided in subfolders:
    - **import**: temporary place to dump ebooks before they are imported into the library proper
    - **imported**: when an ebook is imported (and renamed), a copy of the original is optionnally placed here.
    - **kindle**: a mirror of the library, with all epubs converted into mobis. This is what will be synced with the Kindle.
    - **library**: where all imported ebooks are safely kept.
- *kindle_root*: where the Kindle is mounted when it is connected by USB. This may depend on your Linux distribution.
- *scrape_root*: if you have ebooks lying around on a drive at random, for example, scraping it will copy them all into the import subfolder.

An example configuration would be:

    author_aliases:
        Alexandre Dumas Père: Alexandre Dumas
        China Mieville: China Miéville
        Richard Morgan: Richard K. Morgan
    backup_imported_ebooks: true
    interactive: true
    kindle_documents_subdir: library
    kindle_root: /run/media/login/Kindle
    library_root: /home/login/ebooks
    scrape_root: /home/login/documents
    wanted:
        Harry Harrisson: Make Room! Make Room!

*kindle_root* and *library_root* are mandatory. The rest is optional.
*interactive* decides if importing ebooks is automatic or if manual confirmation
is required for each book.
The *wanted* option is to be seen as a way to keep a wishlist. Librarian.py will
remove the entries it finds on import.

**Note**: Only epub ebooks can be added to the library. They are converted to
mobi while syncing with the Kindle.
If mobi ebooks are present in the *import* folder, they are converted to epub,
then imported. Both the original mobi and the resulting epub are then backed up
in the *imported* folder.

The library database is kept in a Python dictionary saved and loaded as a json
file.

### Usage

Note: if python2 is the default version on your Linux distribution, launch with *python3 librarian.py*.

    $ python librarian.py -h
    usage: librarian.py [-h] [-i] [-r] [-s] [-k] [-f [STRING [STRING ...]]]
                        [-l [STRING [STRING ...]]] [-x STRING [STRING ...]]
                        [-t ADD_TAG [ADD_TAG ...]]
                        [-d DELETE_TAG [DELETE_TAG ...]] [-c [COLLECTIONS]]

    Librarian.

    optional arguments:
    -h, --help            show this help message and exit

    Library management:
    Import, analyze, and sync with Kindle.

    -i, --import          import ebooks
    -r, --refresh         refresh library
    -s, --scrape          scrape for ebooks
    -k, --sync-kindle     sync library (or a subset with --filter or --list)
                          with kindle

    Tagging:
    Search and tag ebooks. For --list, --filter and --exclude, STRING can
    begin with author:, title:, tag:, or series: for a more precise search.

    -f [STRING [STRING ...]], --filter [STRING [STRING ...]]
                            list ebooks in library matching ALL patterns
    -l [STRING [STRING ...]], --list [STRING [STRING ...]]
                            list ebooks in library matching ANY pattern
    -x STRING [STRING ...], --exclude STRING [STRING ...]
                            exclude ALL STRINGS from current list/filter
    -t ADD_TAG [ADD_TAG ...], --add-tag ADD_TAG [ADD_TAG ...]
                            tag listed ebooks in library
    -d DELETE_TAG [DELETE_TAG ...], --delete-tag DELETE_TAG [DELETE_TAG ...]
                            remove tag(s) from listed ebooks in library
    -c [COLLECTIONS], --collections [COLLECTIONS]
                            list all tags or ebooks with a given tag or "untagged"

While syncing with Kindle, *librarian.py* will keep track of previous conversions
to the mobi format (for epub ebooks), and of previously synced ebooks on the Kindle,
and will try to work no more than necessary.

Note that if books are imported successfully, a refresh is automatically added.
Also, only .epubs and .mobis are imported/scraped, with a preference for .epub
when both formats are available.

librarian sync
--------------

This is the part that generates the Kindle collections from a json file.
It can be used completely independantly of librarian.py, provided the
collections.json file is correct (see example later) and in the correct location
(inside the **extensions** folder on the Kindle).

### Requirements

- [A jailbroken Kindle Paperwhite2](http://www.mobileread.com/forums/showthread.php?t=186645)
- [Mobiread Kindlet Kit installed](http://www.mobileread.com/forums/showthread.php?t=233932)
- [KUAL installed](http://www.mobileread.com/forums/showthread.php?t=203326)
- [Python installed](http://www.mobileread.com/forums/showthread.php?t=225030) (snapshot > 0.10N-r10867)

For instructions on how to do that, try the
[mobileread forum](http://www.mobileread.com/forums/forumdisplay.php?f=150) in
general.

This script is inspired by
[this thread](http://www.mobileread.com/forums/showthread.php?t=160855).


### Installation

Once the requirements are met, just copy the librariansync folder into the
**extensions** folder on the kindle.

### Usage

From the Kindle, launch KUAL. A new menu option *Librarian Sync* should appear,
which contains two entries:

- *Rebuild all collections (from json)* :
    to clear all existing collections and rebuild them using the json file
- *Add to collections (from json)* :
    to only add ebooks to existing or new collections, using the json file
- *Rebuild all collections (from folders)* :
    to clear all existing collection and rebuild them using the folder structure
    inside the **documents** folder.


### What it does

After syncing with the main script librarian.py, and if tags are defined in
library.yaml for entries, the **extensions** folder on the Kindle should contain
a file, collections.json.

When *rebuilding collections*, Librarian Sync removes all collections, then adds
the collections as defined in collections.json.

When *adding to them*, it preserves already existing collections, and only either
add entries to them or creates new collections as defined in collections.json.

When *rebuilding collection from folders*, it removes all collections and
recursively scans for any supported file inside the **documents** folder.
Subfolders will be treated as different collections.
Ebooks directly in the **documents** folder are ignored.

Allow for a few seconds for the Kindle database and interface to reflect the
changes made.

### collections.json example

For each path of an ebook (relative to the **documents** folder) is associated a
list of collection names.

    {
        "library/Alexandre Dumas/Alexandre Dumas (2004) Les Trois Mousquetaires.mobi": ["gutenberg","french","already read"],
        "library/Alexandre Dumas/Alexandre Dumas (2004) Vingt Ans Après.mobi": ["gutenberg","french","not read yet"],
        "library/Alexandre Dumas/Alexandre Dumas (2011) Le Comte De Monte-Cristo.mobi": ["gutenberg","french","already read"]
    }

Library Sync creates all of the collections mentionned, then associates the
relevant ebooks to them.
