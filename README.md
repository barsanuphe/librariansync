# LibrarianSync


## What it is

A KUAL script that can automatically build collections based on the tags added
with librarian, according to the folder structure, or based on collections
created with the [Calibre Kindle Collections plugin](http://www.mobileread.com/forums/showthread.php?t=244202).
It should work on all Kindle 5 models (Touch, PaperWhite 1, PaperWhite 2, Voyage, Basic, PaperWhite 3, Oasis, Basic 2, Oasis 2, PaperWhite 4) with
reasonnably recent firmware.

## Table of Contents

- [Requirements](#requirements-1)
- [Installation](#installation)
- [Configuration](#configuration-1)
- [Usage](#usage-1)
- [What it does](#what-it-does)
- [collection.json example](#collectionsjson-example)

### Requirements


- [A JailBroken Device](http://www.mobileread.com/forums/showthread.php?t=186645)
- [Mobiread Kindlet Kit installed](http://www.mobileread.com/forums/showthread.php?t=233932) (should be bundled with most recent JBs)
- [KUAL installed](http://www.mobileread.com/forums/showthread.php?t=203326)
- [Python installed](http://www.mobileread.com/forums/showthread.php?t=195474) (a decently recent enough version, >= 0.11.N)

For instructions on how to do that, try the dedicated
[MobileRead forum](http://www.mobileread.com/forums/forumdisplay.php?f=150) in
general.

Additional information on LibrarianSync can be found in [its very own MobileRead thread](http://www.mobileread.com/forums/showthread.php?p=2903535).


This script is inspired by
[this thread](http://www.mobileread.com/forums/showthread.php?t=160855).

### Installation

Once the requirements are met, just copy the **librariansync** folder into the
**extensions** folder on the kindle.

Alternatively, it is possible to build a kindle update package using
[KindleTool](https://github.com/NiLuJe/KindleTool) by running
*tools/build-librariansync-bin.sh*.
This .bin package is then installable with the [MobileRead Package Installer](http://www.mobileread.com/forums/showthread.php?t=251143).

The [LS MobileRead thread](http://www.mobileread.com/forums/showthread.php?p=2903535) contains packages ready to install.

### Usage

From the Kindle, launch KUAL. A new menu option *Librarian Sync* should appear,
which contains two entries:

- *Rebuild collections (from json)* :
    to clear all existing collections and rebuild them using the json file
- *Update collections (from json)* :
    to only add ebooks to existing or new collections, using the json file
- *Rebuild collections (from folders)* :
    to clear all existing collections and rebuild them using the folder structure
    inside the **documents** folder.
- *Rebuild collections (from calibre plugin json)* :
    to clear all existing collections and rebuild them using a json file generated
    by the [Calibre Kindle Collections plugin](http://www.mobileread.com/forums/showthread.php?t=244202)
- *Update collections (from calibre plugin json)* :
    to only add ebooks to existing or new collections, using a json file generated
    by the [Calibre Kindle Collections plugin](http://www.mobileread.com/forums/showthread.php?t=244202)
- *Export current collections* :
    generates exported_collections.json in the **extensions** folder from current
    collections.
- *Download from librarian*:
    If *librarian* is serving ebooks, retrieves the list of available files,
    downloads them all, retrieves the collections.json for the new ebooks, and
    automatically updates collections.
- *Delete all collections*


### Configuration

*LibrarianSync* only requires configuration when used to download ebooks served
over http by *librarian*.

In the **extensions/librariansync** folder, there should be a *librarian_download.ini*
file such as:

    [server]
    IP = 192.168.0.5|192.168.15.201
    port = 13698


*IP* is a pipe-separated (|) list of IP addresses.
The IP address should be the same as the one given in the *librarian* configuration.

When more than one address is given, *LibrarianSync* tries to connect to each one.
The idea is to be able to download using Wi-Fi or USBNetwork, so the list of IP
addresses can define serveral interfaces of the same server, or different servers.

### What it does

The native format for collections, described [here](#collectionsjson-example),
is expected to be a file named **extensions/collections.json** on a Kindle.


When *rebuilding collections*, LibrarianSync removes all collections, then adds
the collections as defined in collections.json.

When *adding to them*, it preserves already existing collections, and only either
add entries to them or creates new collections as defined in collections.json.

When *rebuilding collection from folders*, it removes all collections and
recursively scans for any supported file inside the **documents** folder.
Subfolders will be treated as different collections.
Ebooks directly in the **documents** folder are ignored.

When *rebuilding collections from Calibre Kindle plugin json*, LibrarianSync
removes all collections, then adds the collections as defined in a
calibre_plugin.json in the **extensions** folder.

When *exporting collections*, a new file, exported_collections.json, is created
from the current collections in the **extensions** folder. This file can be
backed up, modified, and used to *rebuild collections* (if renamed
*collections.json*).
At the same time, another json file is written, to be used with the Calibre
Kindle Collections plugin.

When *downloading from librarian*, it connects (using Wi-Fi or USBNetwork, depending
on your configuration) to the http server temporarily created by *librarian*,
downloads the available ebooks, and updates the collections using information given
by *librarian*.
*LibrarianSync* notifies *librarian* when it is done, and *librarian* shuts down
its server automatically.

Always allow for a few seconds for the Kindle database and interface to reflect the
changes made.

### collections.json example

Each ebook path (relative to the **documents** folder) is associated to a
list of collection names.

If the path begins with *re:*, then it is interpreted as a python regular
expression.
Any ebook matching it will be added to the collections in the associated list.

    {
        "library/Alexandre Dumas/Alexandre Dumas (2004) Les Trois Mousquetaires.mobi": ["gutenberg","french","already read"],
        "library/Alexandre Dumas/Alexandre Dumas (2004) Vingt Ans Après.mobi": ["gutenberg","french","not read yet"],
        "library/Alexandre Dumas/Alexandre Dumas (2011) Le Comte De Monte-Cristo.mobi": ["gutenberg","french","already read"],
        "re:Alexandre Dumas (Père|Fils)": ["dumas"]
    }

