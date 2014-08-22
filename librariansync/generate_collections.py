# -*- coding: utf-8 -*-
import subprocess, json, os, uuid, time

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

def parse_config(config_file):
    return json.load(open(config_file, 'r'), 'utf8')

def update_kinde_db(db_ebooks, db_collections, config_tags):
    # remove all previous collections
    for coll_uuid in db_collections.values():
        send_curl_post( delete_collection_json(coll_uuid) )
    db_collections = {} # raz

    collections_dict = {} # dict [collection uuid] = [ ebook uuids, ]
    for key in config_tags.keys():
        kindle_path = os.path.join(KINDLE_EBOOKS_ROOT, key)

        if kindle_path in db_ebooks.keys():
            eb_uuid = db_ebooks[kindle_path]
            for coll in config_tags[key]:
                if coll not in db_collections.keys():
                    new_coll_uuid = uuid.uuid4()
                    timestamp = int(time.time())
                    #insert new collection dans Entries
                    send_curl_post( insert_new_collection_entry(new_coll_uuid, coll, timestamp) )
                    db_collections[coll] = new_coll_uuid

                # members
                if db_collections[coll] in collections_dict.keys():
                    collections_dict[db_collections[coll]].append(eb_uuid)
                else:
                    collections_dict[db_collections[coll]] = [eb_uuid]

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

def update_cc_db():
    # build dictionaries of ebooks/collections with their uuids
    db_ebooks, db_collections = parse_entries()
    # parse tags json
    config_tags = parse_config(TAGS)
    # update kindle db accordingly
    update_kinde_db(db_ebooks, db_collections, config_tags)

if __name__ == "__main__":
    update_cc_db()
