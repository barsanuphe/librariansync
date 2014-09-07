#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import subprocess, json, os, uuid, time, sys, shutil, locale, codecs, re, syslog
import sqlite3, requests
from collections import defaultdict

#-------- Config
KINDLE_DB_PATH = "/var/local/cc.db"
TAGS = "../collections.json"
CALIBRE_PLUGIN_FILE = "/mnt/us/system/collections.json"
EXPORT = "../exported_collections.json"
KINDLE_EBOOKS_ROOT = "/mnt/us/documents/"

SELECT_COLLECTION_ENTRIES =                 'select p_uuid, p_titles_0_nominal          from Entries where p_type = "Collection"'
SELECT_EBOOK_ENTRIES =                      'select p_uuid, p_location                  from Entries where p_type = "Entry:Item"'
SELECT_EBOOK_ENTRIES_FOR_CALIBRE =          'select p_uuid, p_cdeKey                    from Entries where p_type = "Entry:Item"'
SELECT_EXISTING_COLLECTIONS =               'select i_collection_uuid, i_member_uuid    from Collections'

SUPPORTED_EXTENSIONS = [".azw", ".mobi", ".prc", ".pobi", ".azw3", ".azw6", ".yj", ".azw1", ".tpz", ".pdf", ".txt", ".html", ".htm", ".jpg", ".jpeg", ".azw2"]

#-------- Logging & user feedback (from the K5 Fonts Hack)
# NOTE: Hardcode HACKNAME for now
HACKNAME="librariansync"

# We'll need this to kill stderr
DEVNULL = open(os.devnull, 'wb')
# NOTE: Use subprocess.DEVNULL w/ Python 3.3

# Do the device check dance...
with open('/proc/usid', 'r') as f:
    kusid=f.read()

kmodel=kusid[2:4]
pw_devcodes=['24', '1B', '1D', '1F', '1C', '20']
pw2_devcodes=['D4', '5A', 'D5', 'D6', 'D7', 'D8', 'F2', '17', '60', 'F4', 'F9', '62', '61', '5F']

if kmodel in pw_devcodes or kmodel in pw2_devcodes:
    # PaperWhite 1/2
    SCREEN_X_RES=768
    SCREEN_Y_RES=1024
    EIPS_X_RES=16
    EIPS_Y_RES=24
else:
    # Touch
    SCREEN_X_RES=600
    SCREEN_Y_RES=800
    EIPS_X_RES=12
    EIPS_Y_RES=20
EIPS_MAXCHARS=SCREEN_X_RES / EIPS_X_RES
EIPS_MAXLINES=SCREEN_Y_RES / EIPS_Y_RES

def kh_msg(msg, level='I', show='a', eips_msg=None):
    # Check if we want to trigger an additionnal eips print
    if show == 'q':
        show_eips=False
    elif show == 'v':
        show_eips=True
    else:
        # NOTE: No verbose mode handling
        show_eips=False

    # Unless we specified a different message, print the full message over eips
    if not eips_msg:
        eips_msg=msg

    # Setup syslog
    syslog.openlog('system: {} {}:kh_msg::'.format(level, HACKNAME))
    if level == "E":
        priority = syslog.LOG_ERR
    elif level == "W":
        priority = syslog.LOG_WARNING
    else:
        priority = syslog.LOG_INFO
    priority |= syslog.LOG_LOCAL4
    # Print to log
    syslog.syslog(priority, msg)

    # Do we want to trigger an eips print?
    if show_eips:
        # NOTE: Hardcode the tag
        eips_tag="L"

        # If loglevel is anything else than I, add it to our tag
        if level != "I":
            eips_tag+=" {}".format(level)

        # Add a leading whitespace to avoid starting right at the left edge of the screen...
        eips_tag=" {}".format(eips_tag)

        # Tag our message
        eips_msg="{} {}".format(eips_tag, eips_msg)

        # Pad with blanks
        eips_msg='{0: <{maxchars}}'.format(eips_msg, maxchars=EIPS_MAXCHARS)

        # And print it (bottom of the screen)
        eips_y_pos=EIPS_MAXLINES - 2
        subprocess.call(['eips', '0', str(eips_y_pos), eips_msg], stderr=DEVNULL)

#-------- Existing Kindle database entries
def parse_entries(cursor):
    ebooks = {}
    collections = {}

    cursor.execute(SELECT_COLLECTION_ENTRIES)
    for (uuid, label) in cursor.fetchall():
        collections[label] = uuid

    cursor.execute(SELECT_EBOOK_ENTRIES)
    for (uuid, location) in cursor.fetchall():
        if location is not None:
            ebooks[location] = uuid

    return ebooks, collections

def parse_entries_for_calibre(cursor):
    ebooks = {}
    collections = {}

    cursor.execute(SELECT_COLLECTION_ENTRIES)
    for (uuid, label) in cursor.fetchall():
        collections[label] = uuid

    cursor.execute(SELECT_EBOOK_ENTRIES_FOR_CALIBRE)
    for (uuid, cdeKey) in cursor.fetchall():
        if uuid is not None:
            ebooks[cdeKey] = uuid

    return ebooks, collections

def parse_existing_collections(c):
    existing_collections = defaultdict(list)

    c.execute(SELECT_EXISTING_COLLECTIONS)
    for (collection_uuid, ebook_uuid) in c.fetchall():
        existing_collections[collection_uuid].append(ebook_uuid)

    return existing_collections

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

#-------- Folders
def get_relative_path(path):
    if isinstance(path, str):
        return path.split(KINDLE_EBOOKS_ROOT)[1].decode("utf8")
    else:
        return path.split(KINDLE_EBOOKS_ROOT)[1]

def list_folder_contents():
    folder_contents = {}
    for root, dirs, files in os.walk(KINDLE_EBOOKS_ROOT):
        for f in [ get_relative_path(os.path.join(root, el)) for el in files if os.path.splitext(el.lower())[1] in SUPPORTED_EXTENSIONS]:
            # if not directly in KINDLE_EBOOKS_ROOT
            if get_relative_path(root) != u"":
                folder_contents[f] = [get_relative_path(root)]
    return folder_contents

#-------- Kindle database commands
def is_cloud_aware():
    # Check if the device is CloudCollections aware in order to know which fields to pass...
    with open('/etc/prettyversion.txt', 'r') as f:
        prettyversion = f.read()

    # We just want the human readable version string, not the crap around it
    parsed_version = prettyversion.split(" ")
    fw_version = parsed_version[1]

    # Don't reinvent the wheel
    from distutils.version import LooseVersion
    if LooseVersion(fw_version) >= LooseVersion('5.4.2'):
        return True
    else:
        return False

def delete_collection_json(coll_uuid):
    return  {
                "delete":
                    {
                        "uuid": coll_uuid
                    }
            }

def insert_new_collection_entry(coll_uuid, title, timestamp):
    locale_lang = locale.getdefaultlocale()[0]
    if is_cloud_aware():
        return {
                    "insert":
                        {
                            "type": "Collection",
                            "uuid": str(coll_uuid),
                            "lastAccess": timestamp,
                            "titles": [
                                        {
                                            "display": title,
                                            "direction": "LTR",
                                            "language": locale_lang
                                        }
                                    ],
                            "isVisibleInHome": 1,
                            "isArchived": 0,
                            "collections": None,
                            "collectionCount": None,
                            "collectionDataSetName": str(coll_uuid)
                        }
                 }
    else:
        return {
                    "insert":
                        {
                            "type": "Collection",
                            "uuid": str(coll_uuid),
                            "lastAccess": timestamp,
                            "titles": [
                                        {
                                            "display": title,
                                            "direction": "LTR",
                                            "language": locale_lang
                                        }
                                    ],
                            "isVisibleInHome": 1,
                            "isArchived": 0,
                            "collections": None
                        }
                 }

def update_collections_entry(coll_uuid, members):
    return  {
                "update":
                    {
                        "type": "Collection",
                        "uuid": str(coll_uuid),
                        "members": members
                    }
            }

def update_ebook_entry_if_in_collection(ebook_uuid, number_of_collections):
    return  {
                "update":
                    {
                        "type": "Entry:Item",
                        "uuid": str(ebook_uuid),
                        "collectionCount": number_of_collections
                    }
            }

def send_post_commands(command):
    kh_msg("Sending commands to the framework . . .", 'I', 'v')
    full_command = { "commands": command, "type": "ChangeRequest", "id": 1 }
    r = requests.post("http://localhost:9101/change", data = json.dumps(full_command), headers = {'content-type': 'application/json'} )
    #print full_command
    #print r.json()

#-------- Kindle database update
def actually_update_db(commands, collections_dict):

    # update all 'Collections' entries with new members
    for coll in collections_dict.keys():
        commands.append(update_collections_entry(coll, collections_dict[coll]) )

    # update all Item:Ebook entries that are in at least one Collection,
    # with the number of collections it belongs to.
    ebook_dict = defaultdict(lambda: 0) # { uuid: number_of_collections }
    for coll in collections_dict.keys():
        ebook_uuids = collections_dict[coll]
        for ebook_uuid in ebook_uuids:
            ebook_dict[ebook_uuid] += 1

    # Can't do that on non-Cloud Collections aware FW
    if is_cloud_aware():
        for ebook in ebook_dict.keys():
            commands.append( update_ebook_entry_if_in_collection(ebook, ebook_dict[ebook]) )

    # send all the commands to update the database
    send_post_commands(commands)

def update_kindle_db(cursor, db_ebooks, db_collections, config_tags, complete_rebuild = True):
    commands = []
    if complete_rebuild:
        # remove all previous collections
        for coll_uuid in db_collections.values():
            commands.append( delete_collection_json(coll_uuid) )
        db_collections = {} # raz

        collections_dict = {} # dict [collection uuid] = [ ebook uuids, ]
    else:
        collections_dict = parse_existing_collections(cursor)

    for key in config_tags.keys():
        kindle_path = os.path.join(KINDLE_EBOOKS_ROOT, key)

        if kindle_path in db_ebooks.keys():
            eb_uuid = db_ebooks[kindle_path]
            for coll in config_tags[key]:

                # fw 5.4.5.2: nested collections do not work
                # Top collections on Kindle Home are shown,
                # but the subcollections are invisible

                #if '/' in coll:
                #    collection_hierarchy = coll.split("/")
                #else:
                #    collection_hierarchy = [coll]

                # disabling nested collections for the moment...
                collection_hierarchy = [coll]

                # nested collections
                for (i,subcollection) in enumerate(reversed(collection_hierarchy)):
                    # create Collection if necessary
                    if subcollection not in db_collections.keys():
                        new_coll_uuid = uuid.uuid4()
                        timestamp = int(time.time())
                        # insert new collection in Entries
                        #TODO: if not top collection, p_isVisibleInHome = 0
                        commands.append( insert_new_collection_entry(new_coll_uuid, subcollection, timestamp) )
                        db_collections[subcollection] = new_coll_uuid

                    # lowest collection, directly associated with ebook uuid
                    if i == 0:
                        # update collection members: ebooks
                        if db_collections[subcollection] in collections_dict.keys():
                            if eb_uuid not in collections_dict[db_collections[subcollection]]:
                                collections_dict[db_collections[subcollection]].append(eb_uuid)
                        else:
                            collections_dict[db_collections[subcollection]] = [eb_uuid]

                    # upper collections, nested inside other collections
                    else:
                        # update collection members: subcollections
                        subcollection_to_collection = list(reversed(collection_hierarchy))[i-1] # verify it exists
                        subcollection_to_collection_uuid = collections_dict[db_collections[subcollection_to_collection]] #TODO: verify if it exists

                        if db_collections[subcollection] in collections_dict.keys():
                            if subcollection_to_collection_uuid not in collections_dict[db_collections[subcollection]]:
                                collections_dict[db_collections[subcollection]].append(subcollection_to_collection_uuid)
                        else:
                            collections_dict[db_collections[subcollection]] = [subcollection_to_collection_uuid]

    actually_update_db(commands, collections_dict)

#-------- Main
def update_cc_db(complete_rebuild = True, from_json = True):
    cc_db = sqlite3.connect(KINDLE_DB_PATH)
    c = cc_db.cursor()
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries(c)
    if from_json:
        # parse tags json
        collections_contents = parse_config(TAGS)
    else:
        # parse folder structure
        collections_contents = list_folder_contents()
    # update kindle db accordingly
    update_kindle_db(c, db_ebooks, db_collections, collections_contents, complete_rebuild)

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

def update_cc_db_from_calibre_plugin_json(complete_rebuild = True):
    cc_db = sqlite3.connect(KINDLE_DB_PATH)
    c = cc_db.cursor()
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries_for_calibre(c)
    # parse calibre plugin json
    collection_members_uuid = parse_calibre_plugin_config(CALIBRE_PLUGIN_FILE)

    commands = []
    if complete_rebuild:
        # remove all previous collections
        for coll_uuid in db_collections.values():
            commands.append( delete_collection_json(coll_uuid) )
        db_collections = {} # raz

    collections_dict = defaultdict(list) # dict [collection uuid] = [ ebook uuids, ]

    for collection_label in collection_members_uuid.keys():
        # Rebuild our list of items w/ their actual db uuid, instead of the legacy hash
        ebook_db_uuids = list()
        for cur_hash in collection_members_uuid[collection_label]:
            cdeType, cdeKey = parse_legacy_hash(cur_hash)
            # NOTE: We don't actually use the cdeType. We shouldn't need to, unless we run into the extremely unlikely case of two items with the same cdeKey, but different cdeTypes
            if cdeKey in db_ebooks:
                ebook_db_uuids.append(db_ebooks[cdeKey])
            else:
                print "Couldn't get a DB uuid for cdeKey: {} ! Make sure it's actually on the device.".format(cdeKey)
        if collection_label not in db_collections.keys():
            # create
            new_uuid = uuid.uuid4()
            timestamp = int(time.time())
            # insert new collection in Entries
            commands.append( insert_new_collection_entry(new_uuid, collection_label, timestamp) )
            collections_dict[new_uuid].extend(ebook_db_uuids)
        else:
            collections_dict[db_collections[collection_label]].extend(ebook_db_uuids)

    actually_update_db(commands, collections_dict)

def export_existing_collections():
    cc_db = sqlite3.connect(KINDLE_DB_PATH)
    c = cc_db.cursor()
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries(c)
    # dict [ebook_location] = ebook_uuid
    # dict [collection_label] = collection_uuid

    # dict [ebook_uuid] = ebook_location
    inverted_db_ebooks = {v: k for k, v in db_ebooks.iteritems()}
    # dict [collection_uuid] = collection_label
    inverted_db_collections = {v: k for k, v in db_collections.iteritems()}

    # dict [collection uuid] = [ ebook uuids, ]
    collections_dict = parse_existing_collections(c)
    labels_collections_dict = defaultdict(list) # dict [collection_label] = [ebook locations, ]
    for collection_uuid in collections_dict.keys():
        if collection_uuid in inverted_db_collections.keys():
            labels_collections_dict[inverted_db_collections[collection_uuid]].extend([inverted_db_ebooks[ebook_uuid] for ebook_uuid in collections_dict[collection_uuid] if ebook_uuid in inverted_db_ebooks.keys()])

    export = defaultdict(list) # dict [ebook_location] = [ collection_label ]
    for collection_label, ebook_location_list in labels_collections_dict.items():
        for ebook_location in ebook_location_list:
            export[get_relative_path(ebook_location)].append(collection_label)

    export_json = codecs.open(EXPORT, "w", "utf8")
    export_json.write(json.dumps(export, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))
    export_json.close()

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "add":
        kh_msg("Updating collections (librarian) . . .", 'I', 'v')
        update_cc_db(complete_rebuild = False, from_json = True)
    elif command == "rebuild":
        kh_msg("Rebuilding collections (librarian) . . .", 'I', 'v')
        update_cc_db(complete_rebuild = True, from_json = True)
    elif command == "rebuild_from_folders":
        kh_msg("Rebuilding collections (directory structure) . . .", 'I', 'v')
        update_cc_db(complete_rebuild = True, from_json = False)
    elif command == "update_from_calibre_plugin_json":
        kh_msg("Updating collections (Calibre) . . .", 'I', 'v')
        update_cc_db_from_calibre_plugin_json(complete_rebuild = False)
    elif command == "rebuild_from_calibre_plugin_json":
        kh_msg("Rebuilding collections (Calibre) . . .", 'I', 'v')
        update_cc_db_from_calibre_plugin_json(complete_rebuild = True)
    elif command == "export":
        kh_msg("Exporting collections (Calibre) . . .", 'I', 'v')
        export_existing_collections()
