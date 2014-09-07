import os, locale, time

KINDLE_EBOOKS_ROOT =    "/mnt/us/documents/"

SUPPORTED_EXTENSIONS = [".azw",
                        ".mobi",
                        ".prc",
                        ".pobi",
                        ".azw3",
                        ".azw6",
                        ".yj",
                        ".azw1",
                        ".tpz",
                        ".pdf",
                        ".txt",
                        ".html",
                        ".htm",
                        ".jpg",
                        ".jpeg",
                        ".azw2"]

#-------- Folders
def list_folder_contents():
    folder_contents = {}
    for root, dirs, files in os.walk(KINDLE_EBOOKS_ROOT):
        for f in [ get_relative_path(os.path.join(root, el)) for el in files if os.path.splitext(el.lower())[1] in SUPPORTED_EXTENSIONS]:
            # if not directly in KINDLE_EBOOKS_ROOT
            if get_relative_path(root) != u"":
                folder_contents[f] = [get_relative_path(root)]
    return folder_contents

def get_relative_path(path):
    if isinstance(path, str):
        return path.split(KINDLE_EBOOKS_ROOT)[1].decode("utf8")
    else:
        return path.split(KINDLE_EBOOKS_ROOT)[1]



class Ebook(object):
    def __init__(self, uuid, location, cdekey):
        self.uuid = uuid
        self.location = location
        self.cdekey = cdekey
        self.collections = []

    def add_collection(self, collection):
        self.collections.append(collection)

    def to_librarian_json(self):
        if self.collections == []:
            return {}
        else:
            return { get_relative_path(self.location): [coll.label for coll in self.collections] }

class Collection(object):
    def __init__(self, uuid, label, is_new = False):
        self.uuid = uuid
        self.label = label
        self.ebooks = []
        self.is_new = is_new

    def add_ebook(self, ebook):
        self.ebooks.append(ebook)

    def to_calibre_plugin_json(self):
        if self.ebooks == []:
            return {}
        else:
            return { "%s@%s"%(self.label, locale.getdefaultlocale()[0]):
                        {
                                "items": [e.uuid for e in self.ebooks],
                                "lastAccess": int(time.time())
                        }
                   }


# it would be very, very unlucky to have a collision
# between collection uuid & label...
def find_collection(collections, collection_uuid_or_label):
    for (i,collection) in enumerate(collections):
        if collection.uuid == collection_uuid_or_label or collection.label == collection_uuid_or_label:
            return i
    return -1

# same for uuid & location. Note that we add matching an uuid to a cdeKey in order to handle the legacy json db schema.
def find_ebook(ebooks, ebook_uuid_or_location_or_cdekey):
    for (i,ebook) in enumerate(ebooks):
        if ebook.uuid == ebook_uuid_or_location_or_cdekey or ebook.location == ebook_uuid_or_location_or_cdekey or ebook.cdekey == ebook_uuid_or_location_or_cdekey:
            return i
    return -1
