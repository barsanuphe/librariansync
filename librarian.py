# -*- coding: utf-8 -*-

#TODO: add pattern in config for naming ebooks, something like: $author/$author ($date) $title
#TODO: tolerate missing yaml options
#TODO: check if pyyaml/calibre/python3 are installed and used

#TODO: ADD TAG MARCHE PAS TOUT A FAIT!!!!


import yaml, os, subprocess, shutil, codecs, sys, hashlib, time, concurrent.futures, multiprocessing, marshal

BACKUP_IMPORTED_EBOOKS = False
SCRAPE_ROOT = ""
KINDLE_DOCUMENTS_SUBDIR = "library"  #TODO: yaml option

# library is located next to this script
LIBRARY_DB = os.path.join(os.path.dirname(os.path.realpath(__file__)), "library.db")
LIBRARY_CONFIG = os.path.join(os.path.dirname(os.path.realpath(__file__)), "librarian.yaml")
AUTHOR_ALIASES = {}

def refresh_global_variables():
    global IMPORT_DIR, IMPORTED_DIR, LIBRARY_DIR, KINDLE_DIR, COLLECTIONS, LIBRARY_ROOT
    global KINDLE_DIR, KINDLE_DOCUMENTS, KINDLE_EXTENSIONS, KINDLE_ROOT
    IMPORT_DIR = os.path.join(LIBRARY_ROOT,"import")
    LIBRARY_DIR = os.path.join(LIBRARY_ROOT,"library")
    IMPORTED_DIR = os.path.join(LIBRARY_ROOT,"imported")
    KINDLE_DIR = os.path.join(LIBRARY_ROOT,"kindle")
    COLLECTIONS = os.path.join(LIBRARY_ROOT,"collections.json")
    KINDLE_DOCUMENTS = os.path.join(KINDLE_ROOT, "documents", KINDLE_DOCUMENTS_SUBDIR)
    KINDLE_EXTENSIONS = os.path.join(KINDLE_ROOT, "extensions")

    if not os.path.exists(IMPORT_DIR):
        os.makedirs(IMPORT_DIR)
    if not os.path.exists(IMPORTED_DIR):
        os.makedirs(IMPORTED_DIR)
    if not os.path.exists(LIBRARY_DIR):
        os.makedirs(LIBRARY_DIR)
    if not os.path.exists(KINDLE_DIR):
        os.makedirs(KINDLE_DIR)

class Ebook(object):

    def __init__(self, path):
        self.path = path
        self.is_imported = False
        self.is_metadata_complete = False
        self.author = "Various"
        self.title = "Title"
        self.tags = []
        self.date = 0
        self.format = os.path.splitext(self.path)[1][1:].lower() # extension without the .
        self.was_converted_to_mobi = False
        self.converted_to_mobi_from_hash = ""
        self.converted_to_mobi_hash = ""
        self.last_synced_hash = ""

    @property
    def current_hash(self):
        return hashlib.sha1(open(self.path, 'rb').read()).hexdigest()

    @property
    def filename(self):
        return "%s.%s"%(str(self), self.format.lower())

    @property
    def exported_filename(self):
        return os.path.splitext(self.filename)[0] + ".mobi"

    def read_metadata(self):
        try:
            all_metadata = subprocess.check_output('ebook-meta "%s"'%self.path, shell=True)
            all_metadata = all_metadata.split(b"\n")
            md_dict = {}
            for md in all_metadata:
                parts = md.split(b":")
                md_dict[ parts[0].decode().strip() ] = b":".join(parts[1:]).decode().strip()
        except:
            print("Impossible to read metadata for ", self.path)
            return False

        try:
            self.author = md_dict["Author(s)"].split('[')[0].strip().title()
            if ',' in self.author:
                parts = self.author.split(",")
                if len(parts) == 2:
                    self.author = "%s %s"%(parts[1].strip(), parts[0].strip())
                if len(parts) > 2:
                    self.author = "Various"
            if '&' in self.author:
                self.author = "Various"
            if self.author in list(AUTHOR_ALIASES.keys()):
                self.author = AUTHOR_ALIASES[self.author]

            self.title = md_dict["Title"].replace(":", "").replace("?","").replace("/", "-").title()
            self.date = int(md_dict["Published"][:4])
            self.is_metadata_complete = True
            self.rename_from_metadata()

        except Exception as err:
            print("Incomplete metadata for ", self.path, err)
            return False

        return True

    def rename_from_metadata(self):
        if self.is_metadata_complete and LIBRARY_DIR in self.path:
            new_filename = "%s.%s"%(str(self), self.format.lower())
            new_name = os.path.join(LIBRARY_DIR, new_filename)
            if new_name != self.path:
                if not os.path.exists( os.path.dirname(new_name) ):
                    print("Creating directory", os.path.dirname(new_name) )
                    os.makedirs( os.path.dirname(new_name) )
                print("Renaming to ", new_name)
                shutil.move(self.path, new_name)
                # refresh name
                self.path = new_name

    def export_to_mobi(self):
        output_filename = os.path.join(KINDLE_DIR, self.exported_filename)
        if os.path.exists(output_filename):
            # check if ebook has changed since the mobi was created
            if self.current_hash == self.converted_to_mobi_from_hash:
                self.was_converted_to_mobi = True
                return

        if not os.path.exists( os.path.dirname(output_filename) ):
            print("Creating directory", os.path.dirname(output_filename) )
            os.makedirs( os.path.dirname(output_filename) )

        if self.format == "mobi":
            shutil.copy( self.path, output_filename)
        else:
            #conversion
            print("   + Converting to .mobi: ", self.filename)
            subprocess.call(['ebook-convert "%s" "%s" --output-profile kindle_pw'%(self.path, output_filename)], shell=True, stdout=subprocess.DEVNULL)

        self.converted_to_mobi_hash = hashlib.sha1(open(output_filename, 'rb').read()).hexdigest()
        self.converted_to_mobi_from_hash = self.current_hash
        self.was_converted_to_mobi = True

    def add_to_collection(self, tag):
        if tag.lower() not in self.tags:
            self.tags.append(tag.lower())

    def remove_from_collection(self, tag):
        if tag.lower() in self.tags:
            self.tags.remove(tag.lower())

    def sync_with_kindle(self):
        if not os.path.exists(KINDLE_ROOT):
            print("Kindle is not connected/mounted. Abandon ship.")
            return

        if not os.path.exists(KINDLE_DOCUMENTS):
            os.makedirs(KINDLE_DOCUMENTS)

        if not self.was_converted_to_mobi:
            self.export_to_mobi()

        output_filename = os.path.join(KINDLE_DOCUMENTS, self.exported_filename)

        if not os.path.exists( os.path.dirname(output_filename) ):
            print("Creating directory", os.path.dirname(output_filename) )
            os.makedirs( os.path.dirname(output_filename) )

        # check if exists and with latest hash
        if os.path.exists(output_filename) and self.last_synced_hash == self.converted_to_mobi_hash:
            #print("   - Skipping already synced .mobi: ", self.filename)
            return

        print("   + Syncing: ", self.filename)
        shutil.copy( os.path.join(KINDLE_DIR, self.exported_filename), output_filename)
        self.last_synced_hash = self.converted_to_mobi_hash

    def __str__(self):
        return "%s/%s (%s) %s"%(self.author, self.author, self.date, self.title)

    def to_dict(self):
        return  {
                    "author": self.author, "title": self.title,
                    "path": self.path,  "tags": ",".join([el for el in self.tags if el.strip() != ""]),
                    "format": self.format, "date": self.date,
                    "last_synced_hash": self.last_synced_hash, "converted_to_mobi_hash": self.converted_to_mobi_hash, "converted_to_mobi_from_hash": self.converted_to_mobi_from_hash
                }


    def to_json(self):
        exported_tags = ['"%s"'%tag for tag in self.tags]
        return """\t"%s": [%s],\n"""%(os.path.join(KINDLE_DOCUMENTS_SUBDIR, self.exported_filename), ",".join(exported_tags))

    def try_to_load_from_json(self, everything, filename):
        if not os.path.exists(everything[filename]["path"]):
            print("File %s in DB cannot be found, ignoring."%path)
            return False
        try:
            self.author = everything[filename]['author']
            self.title = everything[filename]['title']
            self.format = everything[filename]['format']
            self.tags = [el.strip() for el in everything[filename]['tags'].split(",") if el.strip() != ""]
            self.date = everything[filename]['date']
            self.converted_to_mobi_hash = everything[filename]['converted_to_mobi_hash']
            self.converted_to_mobi_from_hash = everything[filename]['converted_to_mobi_from_hash']
            self.last_synced_hash = everything[filename]['last_synced_hash']
        except Exception as err:
            print("Incorrect db!", err)
            return False
        return True

class Library(object):
    def __init__(self):
        self.ebooks = []

    def _load_ebook(self, everything, filename):
        if not "path" in list(everything[filename].keys()):
            return False, None
        eb = Ebook(everything[filename]["path"])
        return eb.try_to_load_from_json(everything, filename), eb

    def open_db(self):
        self.db = []

        #configuration
        if os.path.exists(LIBRARY_CONFIG):
            start = time.perf_counter()
            doc = yaml.load(open(LIBRARY_CONFIG, 'r'))
            global KINDLE_ROOT, LIBRARY_ROOT, BACKUP_IMPORTED_EBOOKS, SCRAPE_ROOT
            KINDLE_ROOT = doc["kindle_root"]
            LIBRARY_ROOT = doc["library_root"]
            SCRAPE_ROOT = doc["scrape_root"]
            BACKUP_IMPORTED_EBOOKS = doc["backup_imported_ebooks"]
            refresh_global_variables()
            global AUTHOR_ALIASES
            AUTHOR_ALIASES = doc["author_aliases"]
            print("Config opened in %.3fs."%(time.perf_counter() - start))

        # ebooks
        if os.path.exists(LIBRARY_DB):
            start = time.perf_counter()
            everything = marshal.load(open(LIBRARY_DB, 'rb')) #, 'utf8')

            with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
                future_to_ebook = { executor.submit(self._load_ebook, everything, filename): filename for filename in list(everything.keys())}
                for future in concurrent.futures.as_completed(future_to_ebook):
                    success, ebook = future.result()
                    if success:
                        self.ebooks.append(ebook)

            print("Database opened in %.3fs."%(time.perf_counter() - start))

    def _refresh_ebook(self, full_path, old_db):
        is_already_in_db = False
        for eb in old_db:
            if eb.path == full_path:
                is_already_in_db = True
                eb.read_metadata()
                return eb
        if not is_already_in_db:
            eb = Ebook( full_path )
            eb.read_metadata()
            print(" ->  NEW EBOOK: ", eb)
            return eb
        return None

    def refresh_db(self):
        print("Refreshing library...")
        start = time.perf_counter()
        old_db = [eb for eb in self.ebooks]
        self.ebooks = []

        all_ebooks_in_library_dir = []
        for root, dirs, files in os.walk(LIBRARY_DIR):
            all_ebooks_in_library_dir.extend([os.path.join(root, el) for el in files if el.lower().endswith(".epub") or el.lower().endswith(".mobi")])

        cpt = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            future_to_ebook = { executor.submit(self._refresh_ebook, path, old_db): path for path in all_ebooks_in_library_dir}
            for future in concurrent.futures.as_completed(future_to_ebook):
                if future.result() is not None:
                    print(" %.2f%%"%( 100*cpt/len(all_ebooks_in_library_dir)), end="\r", flush=True)
                    cpt += 1
                    self.ebooks.append( future.result() )

        to_delete = [ eb for eb in old_db if eb not in self.ebooks]
        for eb in to_delete:
           print(" -> DELETED EBOOK: ", eb)

        is_incomplete = self.list_incomplete_metadata()
        print("Database refreshed in %.2fs."%(time.perf_counter() - start))
        return is_incomplete

    def save_db(self):
        start = time.process_time()
        data = {}
        # adding ebooks in alphabetical order
        for ebook in sorted(self.ebooks, key=lambda x: x.filename):
            data[ebook.filename] = ebook.to_dict()

        with open(LIBRARY_DB, "w+b") as data_file:
            #data_file.write(json.dumps( data, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))
            data_file.write(marshal.dumps( data))
        print("Database saved in %.2fs."%(time.process_time() - start))

    def update_kindle_collections(self, outfile):
        # generates the json file that is used
        # by the kual script in librariansync/
        print("Building kindle collections from tags.")
        tags_json = "{\n"
        for eb in sorted(self.ebooks, key=lambda x: x.filename):
            if eb.tags != [""]:
                tags_json += eb.to_json()
        tags_json = tags_json[:-2] # remove last ","
        tags_json += "\n}\n"

        f = codecs.open(outfile, "w", "utf8")
        f.write(tags_json)
        f.close()

    def scrape_dir_for_ebooks(self):
        start = time.perf_counter()
        all_ebooks_in_scrape_dir = []
        print("Finding ebooks in %s..."%SCRAPE_ROOT)
        for root, dirs, files in os.walk(SCRAPE_ROOT):
            all_ebooks_in_scrape_dir.extend([os.path.join(root, el) for el in files if el.lower().endswith(".epub") or el.lower().endswith(".mobi")])

        # if an ebook has an epub and mobi version, only take epub
        filtered_ebooks_in_scrape_dir = []
        for ebook in all_ebooks_in_scrape_dir:
            if os.path.splitext(ebook)[1].lower() == ".epub":
                filtered_ebooks_in_scrape_dir.append(ebook)
            if os.path.splitext(ebook)[1].lower() == ".mobi":
                epub_version = os.path.splitext(ebook)[0] + ".epub"
                if epub_version not in all_ebooks_in_scrape_dir:
                    filtered_ebooks_in_scrape_dir.append(ebook)

        if len(filtered_ebooks_in_scrape_dir) == 0:
           print("Nothing to scrape.")
           return False
        else:
           print("Scraping ", SCRAPE_ROOT)

        for ebook in filtered_ebooks_in_scrape_dir:
            print(" -> Scraping ", os.path.basename(ebook))
            shutil.copyfile(ebook, os.path.join(IMPORT_DIR, os.path.basename(ebook) ) )

        print("Scraped ebooks in %.2fs."%(time.perf_counter() - start))
        return True

    def import_new_ebooks(self):
        all_ebooks = [el for el in os.listdir(IMPORT_DIR) if el.endswith(".epub") or el.endswith(".mobi")]
        if len(all_ebooks) == 0:
           print("Nothing new to import.")
           return False
        else:
           print("Importing.")

        all_already_imported_ebooks = [el for el in os.listdir(IMPORTED_DIR) if el.endswith(".epub") or el.endswith(".mobi")]
        already_imported_hashes = []
        for eb in all_already_imported_ebooks:
           already_imported_hashes.append( hashlib.sha1(open(os.path.join(IMPORTED_DIR, eb), 'rb').read()).hexdigest() )

        start = time.perf_counter()
        imported_count = 0
        for ebook in all_ebooks:
            ebook_candidate_full_path = os.path.join(IMPORT_DIR, ebook)

            # check for duplicate hash
            new_hash = hashlib.sha1(open(ebook_candidate_full_path, 'rb').read()).hexdigest()
            if new_hash in already_imported_hashes:
                print(" -> skipping already imported: ",  ebook )
                continue

            # check for complete metadata
            temp_ebook = Ebook(ebook_candidate_full_path)
            is_complete = temp_ebook.read_metadata()
            if not is_complete:
                print(" -> skipping ebook with incomplete metadata: ",  ebook )
                continue

            # check if book not already in library
            already_in_db = False
            for eb in self.ebooks:
                if eb.author == temp_ebook.author and eb.title == temp_ebook.title:
                    already_in_db = True
                    break
            if already_in_db:
                print(" -> library already contains an entry for: ", temp_ebook.author, " - ", temp_ebook.title, ": ",  ebook )
                continue

            # if all checks are ok, importing
            print(" ->",  ebook )
            # backup
            if BACKUP_IMPORTED_EBOOKS:
                shutil.copyfile( ebook_candidate_full_path, os.path.join(IMPORTED_DIR, ebook ) )
            # import
            shutil.move( ebook_candidate_full_path, os.path.join(LIBRARY_DIR, ebook))
            imported_count +=1
        print("Imported ebooks in %.2fs."%(time.perf_counter() - start))

        if imported_count != 0:
            return True
        else:
            return False

    def rename_from_metadata(self):
        print("Renaming ebooks from metadata, if necessary.")
        for eb in l.ebooks:
            eb.rename_from_metadata()

    def sync_with_kindle(self):
        print("Syncing with kindle.")
        if not os.path.exists(KINDLE_ROOT):
            print("Kindle is not connected/mounted. Abandon ship.")
            return
        start = time.perf_counter()
        # lister les mobi sur le kindle
        print(" -> Listing existing ebooks.")
        all_mobi_ebooks = []
        for root, dirs, files in os.walk(KINDLE_DOCUMENTS):
            all_mobi_ebooks.extend( [os.path.join(root, file) for file in files if os.path.splitext(file)[1] == ".mobi"] )

        # sync books / convert to mobi
        print(" -> Syncing library.")
        cpt = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            all_sync = { executor.submit(eb.sync_with_kindle): eb for eb in sorted(self.ebooks, key=lambda x: x.filename)}
            for future in concurrent.futures.as_completed(all_sync):
                ebook = all_sync[future]
                print(" %.2f%%"%( 100*cpt/len(self.ebooks)), end="\r", flush=True)
                cpt += 1
                # remove ebook from list (exporting previously exported ebook)
                if os.path.join(KINDLE_DOCUMENTS, ebook.exported_filename) in all_mobi_ebooks:
                    all_mobi_ebooks.remove( os.path.join(KINDLE_DOCUMENTS, ebook.exported_filename) )

        # delete mobis on kindle that are not in library anymore
        print(" -> Removing obsolete ebooks.")
        for mobi in all_mobi_ebooks:
            print("    + ", mobi)
            os.remove(mobi)

        # sync collections.json
        print(" -> Generating and copying database for collection generation.")
        self.update_kindle_collections(COLLECTIONS)
        shutil.copy(COLLECTIONS, KINDLE_EXTENSIONS)
        print("Library synced to kindle in in %.2fs."%(time.perf_counter() - start))

    def list_incomplete_metadata(self):
        found_incomplete = False
        incomplete_list = ""
        for eb in self.ebooks:
            if not eb.is_metadata_complete:
                found_incomplete = True
                incomplete_list += " -> %s\n"%eb.path
        if found_incomplete:
            print("Checking for incomplete metadata.")
            print(incomplete_list)
        return found_incomplete

    def search(self, search_string):
        filtered = []
        for eb in self.ebooks:
            if search_string.lower() in eb.author.lower() or search_string.lower() in eb.title.lower():
                print(" -> ", eb)
                filtered.append(eb)
        return filtered

    def search_tag(self, search_tag_string=None):
        filtered = []
        for eb in self.ebooks:
            if search_tag_string == None and eb.tags in [[], [""]]:
                print(" -> ", eb, " is untagged")
                filtered.append(eb)
            elif search_tag_string != None and search_tag_string.lower() in eb.tags:
                print(" -> ", eb)
                filtered.append(eb)
        return filtered

if __name__ == "__main__":

    l = Library()
    l.open_db()

    try:
        arg = sys.argv[1].lower()
        if "s" in arg:
            l.scrape_dir_for_ebooks()
        if "i" in arg:
            if l.import_new_ebooks():
                arg += "r" # force refresh after successful import
        if "r" in arg:
            some_are_incomplete = l.refresh_db()
            if some_are_incomplete:
                print("Fix metadata for these ebooks and run this again.")
                sys.exit(-1)
        if "k" in arg:
            l.sync_with_kindle()
        if "f" in arg:
            assert len(sys.argv) >= 3 and len(sys.argv[2]) > 3
            filtered = l.search(sys.argv[2])
            if "t" in arg:
                assert len(sys.argv) >=4
                new_tag = sys.argv[3].lower()
                for eb in filtered:
                    if new_tag not in eb.tags:
                        print(" -> ", eb, "tagged as", new_tag)
                        eb.tags.append(new_tag)
                    else:
                        print(" -> ", eb, "already tagged as", new_tag, ", nothing to do.")
            if "d" in arg:
                assert len(sys.argv) >=4
                tag_to_remove = sys.argv[3].lower()
                for eb in filtered:
                    if tag_to_remove in eb.tags:
                        print(" -> ", eb, "removed as", tag_to_remove)
                        eb.tags.remove(tag_to_remove)
                    else:
                        print(" -> ", eb, "not tagged as", tag_to_remove, ", nothing to do.")

        if "u" in arg:
            if len(sys.argv) == 3:
                filtered = l.search_tag(sys.argv[2])
            elif len(sys.argv) == 2:
                filtered = l.search_tag()

    except Exception as err:
        print(err)
        print("i, r, s, f, t, u and/or k.")
        sys.exit(-1)

    l.save_db()
