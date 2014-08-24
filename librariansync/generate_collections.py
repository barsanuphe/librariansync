# -*- coding: utf-8 -*-
import subprocess, json, os, uuid, time, sys, shutil

DB = "cc.db" # kindle db name
KINDLE_DB_PATH = "/var/local/%s"%DB # kindle db path
TAGS = "../collections.json"
CC_DUMP = "dump.sql"
KINDLE_EBOOKS_ROOT = "/mnt/us/documents"

ID = 0 # global transaction id

def parse_entries():
    ebooks = {}
    collections = {}
    out = subprocess.check_output("""sqlite3 %s 'select p_uuid,p_titles_0_nominal from Entries where p_type = "Collection"'"""%KINDLE_DB_PATH, shell=True)
    for line in out.splitlines():
        collection_uuid, collection_name = line.split('|')
        collections[collection_name.decode("utf8")] = collection_uuid

    out = subprocess.check_output("""sqlite3 %s 'select p_uuid,p_location from Entries where p_type = "Entry:Item"'"""%KINDLE_DB_PATH, shell=True)
    for line in out.splitlines():
        ebook_uuid, ebook_path = line.split('|')
        ebooks[ebook_path.decode("utf8")] = ebook_uuid

    return ebooks, collections

def parse_existing_collections():
    existing_collections = {}

    out = subprocess.check_output("""sqlite3 %s 'select i_collection_uuid,i_member_uuid from Collections'"""%KINDLE_DB_PATH, shell=True)
    for line in out.splitlines():
        collection_uuid, ebook_uuid = line.split('|')
        if collection_uuid in existing_collections.keys():
            existing_collections[collection_uuid].append(ebook_uuid)
        else:
            existing_collections[collection_uuid] = [ebook_uuid]
    print existing_collections
    return existing_collections

def parse_config(config_file):
    return json.load(open(config_file, 'r'), 'utf8')

def update_kinde_db(db_ebooks, db_collections, config_tags, complete_rebuild = True):

    if complete_rebuild:
        # remove all previous collections
        for coll_uuid in db_collections.values():
            send_curl_post( delete_collection_json(coll_uuid) )
        db_collections = {} # raz

        collections_dict = {} # dict [collection uuid] = [ ebook uuids, ]
    else:
        collections_dict = parse_existing_collections()

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
                    print i, subcollection
                    if subcollection not in db_collections.keys():
                        new_coll_uuid = uuid.uuid4()
                        timestamp = int(time.time())
                        #insert new collection dans Entries
                        #TODO: if not top collection, p_isVisibleInHome = 0
                        send_curl_post( insert_new_collection_entry(new_coll_uuid, subcollection, timestamp) )
                        db_collections[subcollection] = new_coll_uuid
                        print "new, ", new_coll_uuid

                    if i == 0: # ebook collection:
                        print "bottom collection", subcollection
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
                        print "lower", subcollection_to_collection
                        subcollection_to_collection_uuid = collections_dict[db_collections[subcollection_to_collection]] #TODO: verify if it exists

                        if db_collections[subcollection] in collections_dict.keys():
                            if subcollection_to_collection_uuid not in collections_dict[db_collections[subcollection]]:
                                collections_dict[db_collections[subcollection]].append(subcollection_to_collection_uuid)
                        else:
                            collections_dict[db_collections[subcollection]] = [subcollection_to_collection_uuid]

    # update all 'Collections' entries with new members
    for coll in collections_dict.keys():
        send_curl_post( update_collections_entry(coll, collections_dict[coll]) )

def delete_collection_json(coll_uuid):
    return '{"delete":{"uuid":"%s"}}'%coll_uuid

def insert_new_collection_entry(coll_uuid, title, timestamp):
    return '{"insert":{"type":"Collection","uuid":"%s","lastAccess": %s,"titles":[{"display":"%s","direction":"LTR","language":"en-US"}],"isVisibleInHome":true}}'%(coll_uuid, timestamp, title)

def update_collections_entry(coll_uuid, members):
    members_str = ""
    for m in members:
        members_str += '"%s",'%m
    members_str = members_str[:-1]
    return '{"update":{"type":"Collection","uuid":"%s","members":[%s]}}'%(coll_uuid, members_str)

def send_curl_post(command):
    global ID
    full_command = '{ "commands":[' + command + '],"type":"ChangeRequest","id":%s}'%ID
    ID += 1
    curl_command = "curl --data '%s' http://localhost:9101/change --header 'Content-Type:application/json'"%(full_command)
    subprocess.call(curl_command, shell=True)

def update_cc_db(complete_rebuild = True):
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries()
    # parse tags json
    config_tags = parse_config(TAGS)
    # update kindle db accordingly
    update_kinde_db(db_ebooks, db_collections, config_tags, complete_rebuild)

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "add":
        update_cc_db(complete_rebuild = False)
    elif command == "rebuild":
        update_cc_db(complete_rebuild = True)
