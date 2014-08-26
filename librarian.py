# -*- coding: utf-8 -*-

#TODO: add pattern in config for naming ebooks, something like: $author/$author ($date) $title
#TODO: list untagged!
#TODO: sync filtered

from __future__ import print_function #so that parsing this with python2 does not raise SyntaxError
import os, subprocess, shutil, sys, hashlib
import time, concurrent.futures, multiprocessing, json, argparse

import sys
if sys.version_info<(3,0,0):
  sys.stderr.write("You need python 3.0 or later to run this script.\n")
  exit(-1)

try:
    assert subprocess.call("ebook-meta --version", shell=True, stdout=subprocess.DEVNULL) == 0
    assert subprocess.call("ebook-convert --version", shell=True, stdout=subprocess.DEVNULL) == 0
except AssertionError as err:
    print("Calibre must be installed!")
    sys.exit(-1)

try:
    import yaml
except Exception as err:
    print("pyyaml (for python3) must be installed!")
    sys.exit(-1)

# library & config are located next to this script
LIBRARY_DB = os.path.join(os.path.dirname(os.path.realpath(__file__)), "library.json")
LIBRARY_CONFIG = os.path.join(os.path.dirname(os.path.realpath(__file__)), "librarian.yaml")

BACKUP_IMPORTED_EBOOKS = True
SCRAPE_ROOT = None
KINDLE_DOCUMENTS_SUBDIR = "library"
AUTHOR_ALIASES = {}
WANTED = {}

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
        return "%s/%s (%s) %s.%s"%(self.author, self.author, self.date, self.title, self.format.lower())

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
            new_name = os.path.join(LIBRARY_DIR, self.filename)
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
        if self.tags == []:
            return "%s (%s) %s"%(self.author, self.date, self.title)
        else:
            return "%s (%s) %s -- %s"%(self.author, self.date, self.title, ", ".join(self.tags))

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
            self.tags = [el.lower().strip() for el in everything[filename]['tags'].split(",") if el.strip() != ""]
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
        self.open_config()

    def _load_ebook(self, everything, filename):
        if not "path" in list(everything[filename].keys()):
            return False, None
        eb = Ebook(everything[filename]["path"])
        return eb.try_to_load_from_json(everything, filename), eb

    def open_config(self):
        #configuration
        if os.path.exists(LIBRARY_CONFIG):
            self.config = yaml.load(open(LIBRARY_CONFIG, 'r'))
            global KINDLE_ROOT, LIBRARY_ROOT, BACKUP_IMPORTED_EBOOKS, SCRAPE_ROOT, AUTHOR_ALIASES, KINDLE_DOCUMENTS_SUBDIR, WANTED
            try:
                KINDLE_ROOT = self.config["kindle_root"]
                LIBRARY_ROOT = self.config["library_root"]

                if "kindle_documents_subdir" in list(self.config.keys()):
                    KINDLE_DOCUMENTS_SUBDIR = self.config["kindle_documents_subdir"] #TODO check if valid name

                refresh_global_variables()
            except Exception as err:
                print("Missing config option: ", err)
                raise Exception("Invalid configuration file!")

            if "scrape_root" in list(self.config.keys()):
                SCRAPE_ROOT = self.config["scrape_root"]
            if "backup_imported_ebooks" in list(self.config.keys()):
                BACKUP_IMPORTED_EBOOKS = self.config["backup_imported_ebooks"]
            if "author_aliases" in list(self.config.keys()):
                AUTHOR_ALIASES = self.config["author_aliases"]
            if "wanted" in list(self.config.keys()):
                WANTED = self.config["wanted"]

    def save_config(self):
        yaml.dump(self.config, open(LIBRARY_CONFIG, 'w'), indent=4, default_flow_style=False, allow_unicode=True)

    def open_db(self):
        self.db = []
        if os.path.exists(LIBRARY_DB):
            start = time.perf_counter()
            everything = json.load(open(LIBRARY_DB, 'r'))

            with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
                future_to_ebook = { executor.submit(self._load_ebook, everything, filename): filename for filename in list(everything.keys())}
                for future in concurrent.futures.as_completed(future_to_ebook):
                    success, ebook = future.result()
                    if success:
                        self.ebooks.append(ebook)
            print("Database opened in %.2fs: loaded %s ebooks."%( (time.perf_counter() - start), len(self.ebooks) ))
        else:
            print("No DB, refresh!")

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

        if WANTED != {}:
            for ebook in self.ebooks:
                if ebook.author in list(WANTED.keys()) and WANTED[ebook.author] in ebook.title:
                    print("Found WANTED ebook: %s - %s "%(ebook.author,WANTED[ebook.author]) )
                    answer = input("Confirm this is what you were looking for: %s\ny/n? "%ebook)
                    if answer.lower() == "y":
                        print("Removing from wanted list.")
                        del WANTED[ebook.author]
                        self.save_config()

        is_incomplete = self.list_incomplete_metadata()
        print("Database refreshed in %.2fs."%(time.perf_counter() - start))
        return is_incomplete

    def save_db(self):
        data = {}
        # adding ebooks in alphabetical order
        for ebook in sorted(self.ebooks, key=lambda x: x.filename):
            data[ebook.filename] = ebook.to_dict()

        with open(LIBRARY_DB, "w") as data_file:
            data_file.write(json.dumps( data, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))

    def update_kindle_collections(self, outfile):
        # generates the json file that is used
        # by the kual script in librariansync/
        #print("Building kindle collections from tags.")
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
        if SCRAPE_ROOT is None:
            print("scrape_root not defined in librarian.yaml, nothing to do.")
            return

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
        cpt = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            all_sync = { executor.submit(eb.sync_with_kindle): eb for eb in sorted(self.ebooks, key=lambda x: x.filename)}
            for future in concurrent.futures.as_completed(all_sync):
                ebook = all_sync[future]
                print(" %.2f%%"%( 100*cpt/len(self.ebooks)), end="\r", flush=True)
                cpt += 1
                # remove ebook from the list of previously exported ebooks
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
        print("Library synced to kindle in %.2fs."%(time.perf_counter() - start))

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

    def search_ebooks(self, search_string):
        filtered = []
        search_string = search_string.lower()
        for eb in self.ebooks:
            if search_string.startswith("author:"):
                if search_string.split("author:")[1].strip() in eb.author.lower():
                    filtered.append(eb)
            elif search_string.startswith("title:"):
                if search_string.split("title:")[1].strip() in eb.title.lower():
                    filtered.append(eb)
            elif search_string.startswith("tag:"):
                tag_to_search_for = search_string.split("tag:")[1].strip()
                for tag in eb.tags:
                    if tag_to_search_for in tag:
                        filtered.append(eb)
                        break # at least one match is good enough
            elif search_string.lower() in eb.author.lower() or search_string.lower() in eb.title.lower() or search_string.lower() in eb.tags:
                filtered.append(eb)
        return filtered

    def exclude_ebooks(self, ebooks_list, exclude_term):
        filtered = []
        exclude_term = exclude_term.lower()
        for eb in ebooks_list:
            if exclude_term.startswith("author:"):
                if exclude_term.split("author:")[1].strip() not in eb.author.lower():
                    filtered.append(eb)
            elif exclude_term.startswith("title:"):
                if exclude_term.split("title:")[1].strip() not in eb.title.lower():
                    filtered.append(eb)
            elif exclude_term.startswith("tag:"):
                tag_to_search_for = exclude_term.split("tag:")[1].strip()
                not_found = True
                for tag in eb.tags:
                    if tag_to_search_for in tag:
                        not_found = False
                        break
                if not_found:
                    filtered.append(eb)
            elif exclude_term.lower() not in eb.author.lower() and exclude_term.lower() not in eb.title.lower() and exclude_term.lower() not in eb.tags:
                filtered.append(eb)
        return filtered

    def search(self, search_list, exclude_list, additive=False):
        complete_filtered_list_or = []
        complete_filtered_list_and = []
        out = []

        if search_list == []:
            out = self.ebooks
        else:
            for library_filter in search_list:
                filtered = self.search_ebooks(library_filter)
                complete_filtered_list_or.extend([el for el in filtered if el not in complete_filtered_list_or])
                if complete_filtered_list_and == []:
                    complete_filtered_list_and = filtered
                else:
                    complete_filtered_list_and = [el for el in complete_filtered_list_and if el in filtered]
            if additive:
                out =  complete_filtered_list_and
            else:
                out =  complete_filtered_list_or

        if exclude_list is not None:
            for exclude in exclude_list:
                out = self.exclude_ebooks(out, exclude)

        return sorted(out, key=lambda x: x.filename)

    def list_tags(self):
        all_tags = {}
        for ebook in self.ebooks:
            for tag in ebook.tags:
                if tag in list(all_tags.keys()):
                    all_tags[tag] += 1
                else:
                    all_tags[tag] = 1
        return all_tags

if __name__ == "__main__":

    start = time.perf_counter()

    parser = argparse.ArgumentParser(description='Librarian.')

    group_import_export = parser.add_argument_group('Library management', 'Import, analyze, and sync with Kindle.')
    group_import_export.add_argument('-i', '--import', dest='import_ebooks', action='store_true', default = False, help='import ebooks')
    group_import_export.add_argument('-r', '--refresh', dest='refresh', action='store_true', default = False, help='refresh library')
    group_import_export.add_argument('-s', '--scrape', dest='scrape', action='store_true', default = False, help='scrape for ebooks')
    group_import_export.add_argument('-k', '--sync-kindle', dest='kindle', action='store_true', default = False, help='sync library with kindle')

    group_tagging = parser.add_argument_group('Tagging', 'Search and tag ebooks. For --list, --filter and --exclude, STRING can begin with author:, title:, tag: for a more precise search.')
    group_tagging.add_argument('-f', '--filter', dest='filter_ebooks_and', action='store', nargs="*", metavar="STRING", help='list ebooks in library matching ALL patterns')
    group_tagging.add_argument('-l', '--list', dest='filter_ebooks_or', action='store', nargs="*", metavar="STRING", help='list ebooks in library matching ANY pattern')
    group_tagging.add_argument('-x', '--exclude', dest='filter_exclude', action='store', nargs="+", metavar="STRING", help='exclude ALL STRINGS from current list/filter')
    group_tagging.add_argument('-t', '--add-tag', dest='add_tag', action='store', nargs="+", help='tag listed ebooks in library')
    group_tagging.add_argument('-d', '--delete-tag', dest='delete_tag', action='store', nargs="+", help='remove tag(s) from listed ebooks in library')
    group_tagging.add_argument('-c', '--collections', dest='collections', action='store_true', help='list all tags')

    args = parser.parse_args()

    if not len(sys.argv) > 1:
        print("No option selected. Try -h.")
        sys.exit()

    if args.filter_exclude is not None and args.filter_ebooks_and is None and args.filter_ebooks_or is None:
        print("The exclude flag --exclude can only be used with either --list or --filter.")
        sys.exit()

    if (args.add_tag is not None or args.delete_tag is not None) and (args.filter_ebooks_and is None or args.filter_ebooks_and == []) and (args.filter_ebooks_or is None or args.filter_ebooks_or == []) :
        print("Tagging all ebooks, or removing a tag from all ebooks, arguably makes no sense. Use the --list/--filter options to filter among the library.")
        sys.exit()

    try:
        l = Library()
        l.open_db()
    except Exception as err:
        print("Error loading DB: ", err)
        sys.exit(-1)

    try:
        if args.scrape:
            l.scrape_dir_for_ebooks()
        if args.import_ebooks:
            if l.import_new_ebooks():
                args.refresh = True
        if args.refresh:
            some_are_incomplete = l.refresh_db()
            if some_are_incomplete:
                print("Fix metadata for these ebooks and run this again.")
                sys.exit(-1)
        if args.kindle:
            l.sync_with_kindle()

        if args.collections:
            all_tags = l.list_tags()
            for tag in sorted(list(all_tags.keys())):
                print(" -> %s (%s)"%(tag, all_tags[tag]))

        # filtering
        filtered = []
        if args.filter_ebooks_and is not None:
            filtered = l.search(args.filter_ebooks_and, args.filter_exclude, additive = True)
        elif args.filter_ebooks_or is not None:
            filtered = l.search(args.filter_ebooks_or, args.filter_exclude, additive = False)

        # add/remove tags
        if args.add_tag is not None and filtered != []:
            tags = [el.lower() for el in args.add_tag] # sanitize
            for ebook in filtered:
                for tag in tags:
                    if tag not in ebook.tags:
                        ebook.tags.append(tag)
        if args.delete_tag is not None and filtered != []:
            tags = [el.lower() for el in args.delete_tag] # sanitize
            for ebook in filtered:
                for tag in tags:
                    if tag in ebook.tags:
                        ebook.tags.remove(tag)

        for ebook in filtered:
            print(" -> ", ebook)

    except Exception as err:
        print(err)
        sys.exit(-1)

    l.save_db()
    print("Everything done in %.2fs."%(time.perf_counter() - start))
