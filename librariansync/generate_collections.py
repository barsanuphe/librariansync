#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import subprocess, json, os, uuid, sys, shutil, codecs, re, syslog
import sqlite3
from collections import defaultdict

from cc_update import CCUpdate
from kindle_contents import *
from kindle_logging import *

#-------- Config
KINDLE_DB_PATH =        "/var/local/cc.db"
TAGS =                  "../collections.json"
CALIBRE_PLUGIN_FILE =   "/mnt/us/system/collections.json"
EXPORT =                "../exported_collections.json"
KINDLE_EBOOKS_ROOT =    "/mnt/us/documents/"

SELECT_COLLECTION_ENTRIES =    'select p_uuid, p_titles_0_nominal          from Entries where p_type = "Collection"'
SELECT_EBOOK_ENTRIES =         'select p_uuid, p_location, p_cdeKey        from Entries where p_type = "Entry:Item"'
SELECT_EXISTING_COLLECTIONS =  'select i_collection_uuid, i_member_uuid    from Collections'

#-------- Existing Kindle database entries
def parse_entries(cursor):
    db_ebooks = []
    db_collections = []

    cursor.execute(SELECT_COLLECTION_ENTRIES)
    for (uuid, label) in cursor.fetchall():
        db_collections.append(Collection(uuid, label))

    cursor.execute(SELECT_EBOOK_ENTRIES)
    for (uuid, location, cdekey) in cursor.fetchall():
        # only consider user ebooks
        if location is not None and KINDLE_EBOOKS_ROOT in location:
            db_ebooks.append(Ebook(uuid, location, cdekey))

    cursor.execute(SELECT_EXISTING_COLLECTIONS)
    for (collection_uuid, ebook_uuid) in cursor.fetchall():
        collection_idx = find_collection(db_collections, collection_uuid)
        ebook_idx = find_ebook(db_ebooks, ebook_uuid)
        if collection_idx != -1 and ebook_idx != -1:
            db_collections[collection_idx].add_ebook(db_ebooks[ebook_idx])
            db_ebooks[ebook_idx].add_collection(db_collections[collection_idx])

    # remove empty collections:
    db_collections = [c for c in db_collections if len(c.ebooks) != 0]

    return db_ebooks, db_collections

#-------- JSON collections
def parse_config(config_file):
    return json.load(open(config_file, 'r'), 'utf8')

def parse_calibre_plugin_config(config_file):
    calibre_plugin_config = json.load(open(config_file, 'r'), 'utf8')
    # Handle the locale properly (it might not be here, or the collection name might contain an @, so split doesn't cut it). RegEx borrowed from the KCP.
    coll_name_pattern = re.compile(r'^(.*)@[^@]+$')
    collection_names = [coll_name_pattern.sub(r'\1', el) for el in calibre_plugin_config.keys()]
    collection_members_uuid = defaultdict(list) # collection_label: [ebook_uuid, ...]
    for collection in calibre_plugin_config.keys():
        collection_members_uuid[coll_name_pattern.sub(r'\1', collection)].extend( calibre_plugin_config[collection]["items"])
    return collection_members_uuid

def update_lists_from_librarian_json(db_ebooks, db_collections, collection_contents):

    for (ebook_location, ebook_collection_labels_list) in collection_contents.items():
        #find ebook by location
        ebook_idx = find_ebook(db_ebooks, os.path.join(KINDLE_EBOOKS_ROOT,ebook_location))
        if ebook_idx == -1:
            print("Invalid location", ebook_location)
            continue # invalid
        for collection_label in ebook_collection_labels_list:
            # find collection by label
            collection_idx = find_collection(db_collections, collection_label)
            if collection_idx == -1:
                # creating new collection object
                db_collections.append(Collection(uuid.uuid4(), collection_label, is_new = True))
                collection_idx = len(db_collections)-1
            # udpate ebook
            db_ebooks[ebook_idx].add_collection(db_collections[collection_idx])
            # update collection
            db_collections[collection_idx].add_ebook(db_ebooks[ebook_idx])

    # remove empty collections:
    db_collections = [c for c in db_collections if len(c.ebooks) != 0]

    return db_ebooks, db_collections

# Return a cdeType, cdeKey couple from a legacy json hash
def parse_legacy_hash(legacy_hash):
    if legacy_hash.startswith('#'):
        cdeKey, cdeType = legacy_hash[1:].split('^')
    else:
        # Legacy md5 hash of the full path, there's no cdeType, assume EBOK.
        # NOTE: If we ever need a real cdeType, do it properly by getting it from the db, and not the json
        cdeType = u'EBOK'
        cdeKey = legacy_hash
    return cdeType, cdeKey

def update_lists_from_calibre_plugin_json(db_ebooks, db_collections, collection_contents):

    for (collection_label, ebook_uuids_list) in collection_contents.items():
        # find collection by label
        collection_idx = find_collection(db_collections, collection_label)
        if collection_idx == -1:
            # creating new collection object
            db_collections.append(Collection(uuid.uuid4(), collection_label, is_new = True))
            collection_idx = len(db_collections)-1
        for ebook_uuid in ebook_uuids_list:
            cdeType, ebook_uuid = parse_legacy_hash(ebook_uuid)
            # NOTE: We don't actually use the cdeType. We shouldn't need to, unless we run into the extremely unlikely case of two items with the same cdeKey, but different cdeTypes
            #find ebook by uuid
            ebook_idx = find_ebook(db_ebooks, ebook_uuid)
            if ebook_idx == -1:
                print("Invalid uuid", ebook_uuid)
                continue # invalid
            # udpate ebook
            db_ebooks[ebook_idx].add_collection(db_collections[collection_idx])
            # update collection
            db_collections[collection_idx].add_ebook(db_ebooks[ebook_idx])

    # remove empty collections:
    db_collections = [c for c in db_collections if len(c.ebooks) != 0]

    return db_ebooks, db_collections

#-------- Main
def update_cc_db(c, complete_rebuild = True, source = "folders"):
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries(c)

    # object that will handle all db updates
    cc = CCUpdate()

    if complete_rebuild:
        # clear all current collections
        for (i, eb) in enumerate(db_ebooks):
            db_ebooks[i].collections = []
        for (i, eb) in enumerate(db_collections):
            db_collections[i].ebooks = []
        for collection in db_collections:
            cc.delete_collection(collection.uuid)
        db_collections = []

    if source == "calibre_plugin":
        collections_contents = parse_calibre_plugin_config(CALIBRE_PLUGIN_FILE)
        db_ebooks, db_collections = update_lists_from_calibre_plugin_json(db_ebooks, db_collections, collections_contents)
    else:
        if source == "folders":
            # parse folder structure
            collections_contents = list_folder_contents()
        else:
            # parse tags json
            collections_contents = parse_config(TAGS)
        db_ebooks, db_collections = update_lists_from_librarian_json(db_ebooks, db_collections, collections_contents)

    # updating collections, creating them if necessary
    for collection in db_collections:
        if collection.is_new:
            # create new collections in db
            cc.insert_new_collection_entry(collection.uuid, collection.label)
        # update all 'Collections' entries with new members
        cc.update_collections_entry(collection.uuid, [e.uuid for e in collection.ebooks])

    # if firmware requires updating ebook entries
    if cc.is_cc_aware:
        # update all Item:Ebook entries with the number of collections it belongs to.
        for ebook in db_ebooks:
            cc.update_ebook_entry(ebook.uuid, len(ebook.collections))

    # send all the commands to update the database
    cc.execute()

def export_existing_collections(c):
    db_ebooks, db_collections = parse_entries(c)

    export = {}
    for ebook in db_ebooks:
        export.update(ebook.to_librarian_json())

    with codecs.open(EXPORT, "w", "utf8") as export_json:
        export_json.write(json.dumps(export, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))

    export = {}
    for collection in db_collections:
        export.update(collection.to_calibre_plugin_json())

    with codecs.open(CALIBRE_PLUGIN_FILE, "w", "utf8") as export_json:
        export_json.write(json.dumps(export, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))

def delete_all_collections(c):
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries(c)

    # object that will handle all db updates
    cc = CCUpdate()
    for collection in db_collections:
        cc.delete_collection(collection.uuid)
    cc.execute()

#-------------------------------------------------------

if __name__ == "__main__":
    command = sys.argv[1]
    try:
        with sqlite3.connect(KINDLE_DB_PATH) as cc_db:
            c = cc_db.cursor()
            if command == "add":
                kh_msg("Updating collections (librarian) . . .", 'I', 'v')
                update_cc_db(c, complete_rebuild = False, source = "librarian")
            elif command == "rebuild":
                kh_msg("Rebuilding collections (librarian) . . .", 'I', 'v')
                update_cc_db(c, complete_rebuild = True, source = "librarian")
            elif command == "rebuild_from_folders":
                kh_msg("Rebuilding collections (directory structure) . . .", 'I', 'v')
                update_cc_db(c, complete_rebuild = True, source = "folders")
            elif command == "rebuild_from_calibre_plugin_json":
                kh_msg("Rebuilding collections (Calibre) . . .", 'I', 'v')
                update_cc_db(c, complete_rebuild = True, source = "calibre_plugin")
            elif command == "rebuild_from_calibre_plugin_json":
                kh_msg("Updating collections (Calibre) . . .", 'I', 'v')
                update_cc_db(c, complete_rebuild = False, source = "calibre_plugin")
            elif command == "export":
                kh_msg("Exporting collections . . .", 'I', 'v')
                export_existing_collections(c)
            elif command == "delete":
                kh_msg("Deleting all collections . . .", 'I', 'v')
                delete_all_collections(c)
    except:
        kh_msg("Something went wrong.", 'I', 'v')