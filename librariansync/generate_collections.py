# -*- coding: utf-8 -*-
import subprocess, json, os, uuid, time, sys, shutil
import sqlite3, requests

KINDLE_DB_PATH = "/var/local/cc.db"
TAGS = "../collections.json"
KINDLE_EBOOKS_ROOT = "/mnt/us/documents"

SELECT_COLLECTION_ENTRIES =     'select p_uuid, p_titles_0_nominal          from Entries where p_type = "Collection"'
SELECT_EBOOK_ENTRIES =          'select p_uuid, p_location                  from Entries where p_type = "Entry:Item"'
SELECT_EXISTING_COLLECTIONS =   'select i_collection_uuid, i_member_uuid    from Collections'

ID = 0 # global transaction id

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
    existing_collections = {}

    c.execute(SELECT_EXISTING_COLLECTIONS)
    for (collection_uuid, ebook_uuid) in c.fetchall():
        if collection_uuid in existing_collections.keys():
            existing_collections[collection_uuid].append(ebook_uuid)
        else:
            existing_collections[collection_uuid] = [ebook_uuid]

    return existing_collections

def parse_config(config_file):
    return json.load(open(config_file, 'r'), 'utf8')

def update_kinde_db(cursor, db_ebooks, db_collections, config_tags, complete_rebuild = True):

    if complete_rebuild:
        # remove all previous collections
        for coll_uuid in db_collections.values():
            update_kindle_db( delete_collection_json(coll_uuid) )
        db_collections = {} # raz

        collections_dict = {} # dict [collection uuid] = [ ebook uuids, ]
    else:
        collections_dict = parse_existing_collections(cursor)

    for key in config_tags.keys():
        kindle_path = os.path.join(KINDLE_EBOOKS_ROOT, key)

        if kindle_path in db_ebooks.keys():
            eb_uuid = db_ebooks[kindle_path]
            for coll in config_tags[key]:

                # fw 5.4.5.2: nested collections do not work (all are visible on home, but not displayed
                # inside the parent collection)

                #if '/' in coll:
                #    collection_hierarchy = coll.split("/")
                #else:
                #    collection_hierarchy = [coll]

                # disabling nested collections for the moment...
                collection_hierarchy = [coll]

                # nested collections
                for (i,subcollection) in enumerate(reversed(collection_hierarchy)):
                    # create if necessary
                    if subcollection not in db_collections.keys():
                        new_coll_uuid = uuid.uuid4()
                        timestamp = int(time.time())
                        #insert new collection dans Entries
                        #TODO: if not top collection, p_isVisibleInHome = 0
                        update_kindle_db( insert_new_collection_entry(new_coll_uuid, subcollection, timestamp) )
                        db_collections[subcollection] = new_coll_uuid

                    if i == 0: # ebook collection:
                        # update collection members: ebooks
                        if db_collections[subcollection] in collections_dict.keys():
                            if eb_uuid not in collections_dict[db_collections[subcollection]]:
                                collections_dict[db_collections[subcollection]].append(eb_uuid)
                        else:
                            collections_dict[db_collections[subcollection]] = [eb_uuid]
                    else:
                        print "top/inter collection", subcollection
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
        update_kindle_db( update_collections_entry(coll, collections_dict[coll]) )

def delete_collection_json(coll_uuid):
    return {"delete": {"uuid": coll_uuid }}

def insert_new_collection_entry(coll_uuid, title, timestamp):
    return { "insert": {"type": "Collection", "uuid": str(coll_uuid), "lastAccess": timestamp, "titles": [{"display": title, "direction": "LTR", "language": "en-US"}], "isVisibleInHome": 1} }

def update_collections_entry(coll_uuid, members):
    members_str = ""
    for m in members:
        members_str += '%s,'%m
    members_str = members_str[:-1]
    return {"update": {"type": "Collection","uuid": str(coll_uuid), "members": [members_str]}}

def update_kindle_db(command):
    global ID
    full_command = { "commands": [command],"type":"ChangeRequest","id": ID}
    ID += 1
    print full_command
    r = requests.post("http://localhost:9101/change", data = json.dumps(full_command), headers = {'content-type': 'application/json'} )
    print r.url
    print r.json()
    print r.json()["ok"]


def update_cc_db(complete_rebuild = True):
    cc_db = sqlite3.connect(KINDLE_DB_PATH)
    c = cc_db.cursor()
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries(c)
    # parse tags json
    config_tags = parse_config(TAGS)
    # update kindle db accordingly
    update_kinde_db(c, db_ebooks, db_collections, config_tags, complete_rebuild)

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "add":
        update_cc_db(complete_rebuild = False)
    elif command == "rebuild":
        update_cc_db(complete_rebuild = True)
