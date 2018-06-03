import os
import requests
import time
import json
import locale
from kindle_logging import log, LIBRARIAN_SYNC


def is_cc_aware():
    # Check if the device is CloudCollections aware in order to know
    # which fields to pass...
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


class CCUpdate(object):
    def __init__(self):
        self.commands = []
        self.is_cc_aware = is_cc_aware()

    def delete_collection(self, coll_uuid):
        self.commands.append(
            {
                "delete":
                    {
                        "uuid": coll_uuid
                    }
            })

    def insert_new_collection_entry(self, coll_uuid, title):
        locale_lang = locale.getdefaultlocale()[0]
        timestamp = int(time.time())
        json_dict = {
            "insert":
            {
                "type": "Collection",
                "uuid": str(coll_uuid),
                "lastAccess": timestamp,
                "titles":
                    [
                        {
                            "display": title,
                            "direction": "LTR",
                            "language": locale_lang
                        }
                    ],
                "isVisibleInHome": 1,
                "isArchived": 0,
                "mimeType": "application/x-kindle-collection",
                "collections": None
            }
        }

        if self.is_cc_aware:
            json_dict["insert"].update(
                {
                    "collectionCount": None,
                    "collectionDataSetName": str(coll_uuid),
                    "isArchived": 1
                })
        self.commands.append(json_dict)

    def update_collections_entry(self, coll_uuid, members):
        self.commands.append(
            {
                "update":
                    {
                        "type": "Collection",
                        "uuid": str(coll_uuid),
                        "members": members
                    }
            })

    def update_ebook_entry(self, ebook_uuid, number_of_collections):
        if number_of_collections != 0:
            self.commands.append(
                {
                    "update":
                        {
                            "type": "Entry:Item",
                            "uuid": str(ebook_uuid),
                            "collectionCount": number_of_collections
                        }
                })

    def execute(self):
        if not self.commands:
            log(LIBRARIAN_SYNC, "cc_update", "Nothing to update.")
        else:
            log(LIBRARIAN_SYNC, "cc_update", "Sending commands...")
            full_command = {"commands": self.commands,
                            "type": "ChangeRequest", "id": 1}
            # When WiFi's enabled, we inherit the WhisperSync proxy, which we *cannot* go through,
            # since we're talking to a local service. So make sure we do *NOT* use any proxies.
            # Turns out that this is *slightly* tricky to achieve with requests,
            # c.f., https://github.com/requests/requests/issues/879#issuecomment-10001977
            os.environ['no_proxy'] = '127.0.0.1,localhost'
            r = requests.post("http://127.0.0.1:9101/change",
                              data=json.dumps(full_command),
                              headers={'content-type': 'application/json'},
                              proxies={'no': 'pass'})
            if r.status_code == requests.codes.ok and r.json()[u"ok"]:
                log(LIBRARIAN_SYNC, "cc_update", "Success.")
            else:
                log(LIBRARIAN_SYNC, "cc_update", "Oh, no. It failed.", "E")
