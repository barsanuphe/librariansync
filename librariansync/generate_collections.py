# -*- coding: utf-8 -*-

import subprocess, json, os, uuid, time, sys, shutil, locale
import sqlite3, requests
from collections import defaultdict

#-------- Config
KINDLE_DB_PATH = "/var/local/cc.db"
TAGS = "../collections.json"
KINDLE_EBOOKS_ROOT = "/mnt/us/documents/"

SELECT_COLLECTION_ENTRIES =     'select p_uuid, p_titles_0_nominal          from Entries where p_type = "Collection"'
SELECT_EBOOK_ENTRIES =          'select p_uuid, p_location                  from Entries where p_type = "Entry:Item"'
SELECT_EXISTING_COLLECTIONS =   'select i_collection_uuid, i_member_uuid    from Collections'

SUPPORTED_EXTENSIONS = [".azw", ".mobi", ".prc", ".pobi", ".azw3", ".azw6", ".yj", ".azw1", ".tpz", ".pdf", ".txt", ".html", ".htm", ".jpg", ".jpeg"]

#-------- Existing Kindle database entries
def parse_entries(cursor):
    ebooks = {}
    collections = {}

    cursor.execute(SELECT_COLLECTION_ENTRIES)
    for (uuid, label) in cursor.fetchall():
        collections[label] = uuid

    cursor.execute(SELECT_EBOOK_ENTRIES)
    for (uuid, label) in cursor.fetchall():
        if label is not None:
            ebooks[label] = uuid

    return ebooks, collections

def parse_existing_collections():
    existing_collections = defaultdict(list)

    c.execute(SELECT_EXISTING_COLLECTIONS)
    for (collection_uuid, ebook_uuid) in c.fetchall():
        existing_collections[collection_uuid].append(ebook_uuid)

    return existing_collections

#-------- JSON collections
def parse_config(config_file):
    return json.load(open(config_file, 'r'), 'utf8')

#-------- Folders
def get_relative_path(path):
    return path.split(KINDLE_EBOOKS_ROOT)[1].decode("utf8")

def list_folder_contents():
    folder_contents = {}
    for root, dirs, files in os.walk(KINDLE_EBOOKS_ROOT):
        for f in [ get_relative_path(os.path.join(root, el)) for el in files if os.path.splitext(el.lower())[1] in SUPPORTED_EXTENSIONS]:
            # if not directly in KINDLE_EBOOKS_ROOT
            if get_relative_path(root) != u"":
                folder_contents[f] = [get_relative_path(root)]
    return folder_contents

#-------- Kindle database commands
def delete_collection_json(coll_uuid):
    return  {
                "delete":
                    {
                        "uuid": coll_uuid
                    }
            }

def insert_new_collection_entry(coll_uuid, title, timestamp):
    locale_lang = locale.getdefaultlocale()[0]
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
    full_command = { "commands": command,"type":"ChangeRequest","id": 1}
    r = requests.post("http://localhost:9101/change", data = json.dumps(full_command), headers = {'content-type': 'application/json'} )
    #print full_command
    #print r.json()

#-------- Kindle database update
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
                        #insert new collection dans Entries
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

                    # upper collections, nested inside other collections.
                    else:
                        # update collection members: subcollections
                        subcollection_to_collection = list(reversed(collection_hierarchy))[i-1] # verify it exists
                        subcollection_to_collection_uuid = collections_dict[db_collections[subcollection_to_collection]] #TODO: verify if it exists

                        if db_collections[subcollection] in collections_dict.keys():
                            if subcollection_to_collection_uuid not in collections_dict[db_collections[subcollection]]:
                                collections_dict[db_collections[subcollection]].append(subcollection_to_collection_uuid)
                        else:
                            collections_dict[db_collections[subcollection]] = [subcollection_to_collection_uuid]

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

    for ebook in ebook_dict.keys():
        commands.append( update_ebook_entry_if_in_collection(ebook, ebook_dict[ebook]) )

    # send all the commands to update the database
    send_post_commands(commands)

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

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "add":
        update_cc_db(complete_rebuild = False, from_json = True)
    elif command == "rebuild":
        update_cc_db(complete_rebuild = True, from_json = True)
    elif command == "rebuild_from_folders":
        update_cc_db(complete_rebuild = True, from_json = False)