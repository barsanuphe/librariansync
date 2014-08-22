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
