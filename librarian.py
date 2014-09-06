#!/usr/bin/python
# -*- coding: utf-8 -*-

#TODO: filename template: support for optional parts (ex: "[$s] [#$i]")
#TODO: support for several series?
#TODO: tags == dc:subject list?
#TODO: auto-correct option (w/author_aliases) + yaml option confirm_before_write
#TODO: allow syncing without converting to mobi (--sync --kindle would convert and sync)
#TODO: try to query google books too
#TODO: when querying by series, order by series_index
#TODO: when displaying lists/info, json mode?
#TODO: wanted list support for multiple books for each author

from __future__ import print_function #so that parsing this with python2 does not raise SyntaxError
import os, subprocess, shutil, sys, hashlib, zipfile
import xml.dom.minidom, codecs
import time, concurrent.futures, multiprocessing, json, argparse

from librarianlib.epub import Epub, read, not_read, reading
from librarianlib.ebook_search import EbookSearch, fuzzy_search_in_list
from librarianlib.openlibrary_search import OpenLibrarySearch



if sys.version_info < (3,0,0):
  print("You need python 3.0 or later to run this script.")
  sys.exit(-1)

try:
    assert subprocess.call(["ebook-convert","--version"], stdout=subprocess.DEVNULL) == 0
except AssertionError as err:
    print("Calibre must be installed for epub -> mobi conversions!")
    sys.exit(-1)

try:
    import yaml
except Exception as err:
    print("pyyaml (for python3) must be installed!")
    sys.exit(-1)

# library & config are located next to this script
librarian_dir = os.path.dirname(os.path.realpath(__file__))
LIBRARY_DB = os.path.join(librarian_dir, "library.json")
LIBRARY_CONFIG = os.path.join(librarian_dir, "librarian.yaml")

KINDLE_DOCUMENTS_SUBDIR = "library"
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

class Library(object):
    def __init__(self):
        self.ebooks = []
        self.backup_imported_ebooks = True
        self.scrape_root = None
        self.wanted = {}
        self.interactive = False
        self.ebook_filename_template = "$a/$a ($y) $t"
        self.open_config()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # cleaning up temp opf files
        for epub in self.ebooks:
            if epub.is_opf_open:
                epub.close_metadata()

    def open_config(self):
        #configuration
        if os.path.exists(LIBRARY_CONFIG):
            self.config = yaml.load(open(LIBRARY_CONFIG, 'r'))
            global KINDLE_ROOT, LIBRARY_ROOT, AUTHOR_ALIASES, KINDLE_DOCUMENTS_SUBDIR
            try:
                KINDLE_ROOT = self.config["kindle_root"]
                LIBRARY_ROOT = self.config["library_root"]

                if "kindle_documents_subdir" in self.config.keys():
                    KINDLE_DOCUMENTS_SUBDIR = self.config["kindle_documents_subdir"] #TODO check if valid name

                refresh_global_variables()
            except Exception as err:
                print("Missing config option: ", err)
                raise Exception("Invalid configuration file!")

            if "scrape_root" in self.config.keys():
                self.scrape_root = self.config["scrape_root"]
            if "backup_imported_ebooks" in self.config.keys():
                self.backup_imported_ebooks = self.config["backup_imported_ebooks"]
            if "author_aliases" in self.config.keys():
                AUTHOR_ALIASES = self.config["author_aliases"]
            if "wanted" in self.config.keys():
                self.wanted = self.config["wanted"]
            if "interactive" in self.config.keys():
                self.interactive = self.config["interactive"]
            self.ebook_filename_template = self.config.get("ebook_filename_template", "$a/$a ($y) $t")

    def save_config(self):
        yaml.dump(self.config, open(LIBRARY_CONFIG, 'w'), indent=4, default_flow_style=False, allow_unicode=True)

    def _load_ebook(self, everything, filename):
        if not "path" in everything[filename].keys():
            return False, None
        eb = Epub(everything[filename]["path"], LIBRARY_DIR, AUTHOR_ALIASES, self.ebook_filename_template)
        return eb.load_from_database_json(everything[filename], filename), eb

    def open_db(self):
        self.db = []
        if os.path.exists(LIBRARY_DB):
            start = time.perf_counter()
            everything = json.load(open(LIBRARY_DB, 'r'))

            with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
                future_to_ebook = { executor.submit(self._load_ebook, everything, filename): filename for filename in everything.keys()}
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
                eb.open_metadata()
                return eb
        if not is_already_in_db:
            eb = Epub( full_path, LIBRARY_DIR, AUTHOR_ALIASES, self.ebook_filename_template )
            eb.open_metadata()
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
            all_ebooks_in_library_dir.extend([os.path.join(root, el) for el in files if el.lower().endswith(".epub")])

        cpt = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            future_to_ebook = { executor.submit(self._refresh_ebook, path, old_db): path for path in all_ebooks_in_library_dir}
            for future in concurrent.futures.as_completed(future_to_ebook):
                if future.result() is not None:
                    print(" %.2f%%"%( 100*cpt/len(all_ebooks_in_library_dir)), end="\r", flush=True)
                    cpt += 1
                    self.ebooks.append( future.result() )

        # not multithreaded to avoir concurrent folder creation
        for eb in self.ebooks:
            eb.rename_from_metadata()

        to_delete = [ eb for eb in old_db if eb not in self.ebooks]
        for eb in to_delete:
           print(" -> DELETED EBOOK: ", eb)

        # remove empty dirs in LIBRARY_DIR
        for root, dirs, files in os.walk(LIBRARY_DIR, topdown=False):
            for dir in [os.path.join(root, el) for el in dirs if os.listdir( os.path.join(root, el)) == []]:
                os.rmdir(dir)

        # check if imported ebook was on wishlist
        if self.wanted != {}:
            for ebook in self.ebooks:
                for key in self.wanted.keys():
                    if fuzzy_search_in_list(key, ebook.metadata.get_values("author")) and fuzzy_search_in_list(self.wanted[key], ebook.metadata.get_values("title")):
                        print("! Found WANTED ebook: ", ebook )
                        answer = input("! Confirm this is what you were looking for: %s\ny/n? "%ebook)
                        if answer.lower() == "y":
                            print(" -> Removing from wanted list.")
                            del self.wanted[key]
                            self.save_config()

        is_incomplete = self.list_incomplete_metadata()
        print("Database refreshed in %.2fs."%(time.perf_counter() - start))
        return is_incomplete

    def save_db(self):
        data = {}
        # adding ebooks in alphabetical order
        for ebook in sorted(self.ebooks, key=lambda x: x.filename):
            data[ebook.filename] = ebook.to_database_json()
        # dumping in json file
        with open(LIBRARY_DB, "w") as data_file:
            data_file.write(json.dumps( data, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))

    def scrape_dir_for_ebooks(self):
        if self.scrape_root is None:
            print("scrape_root not defined in librarian.yaml, nothing to do.")
            return

        start = time.perf_counter()
        all_ebooks_in_scrape_dir = []
        print("Finding ebooks in %s..."%self.scrape_root)
        for root, dirs, files in os.walk(self.scrape_root):
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
           print("Scraping ", self.scrape_root)

        for ebook in filtered_ebooks_in_scrape_dir:
            print(" -> Scraping ", os.path.basename(ebook))
            shutil.copyfile(ebook, os.path.join(IMPORT_DIR, os.path.basename(ebook) ) )

        print("Scraped ebooks in %.2fs."%(time.perf_counter() - start))
        return True

    def _convert_to_epub_before_importing(self, mobi):
        if not os.path.exists(mobi.replace(".mobi",".epub")):
            print("   + Converting to .epub: ", mobi)
            return subprocess.call(['ebook-convert', mobi, mobi.replace(".mobi", ".epub"), "--output-profile", "kindle_pw"], stdout=subprocess.DEVNULL)
        else:
            return 0

    def import_new_ebooks(self):
        # multithreaded conversion to epub before import, if necessary
        cpt = 1
        all_mobis = [os.path.join(IMPORT_DIR, el) for el in os.listdir(IMPORT_DIR) if el.endswith(".mobi")]
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            future_epubs = { executor.submit(self._convert_to_epub_before_importing, mobi): mobi for mobi in all_mobis}
            for future in concurrent.futures.as_completed(future_epubs):
                if future.result() == 0:
                    print(" %.2f%%"%( 100*cpt/len(all_mobis)), end="\r", flush=True)
                    cpt += 1
                else:
                    raise Exception("Error converting to epub!")

        all_ebooks = [el for el in os.listdir(IMPORT_DIR) if el.endswith(".epub")]
        if len(all_ebooks) == 0:
           print("Nothing new to import.")
           return False
        else:
           print("Importing.")

        all_already_imported_ebooks = [el for el in os.listdir(IMPORTED_DIR) if el.endswith(".epub")]
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
            temp_ebook = Epub(ebook_candidate_full_path, LIBRARY_DIR, AUTHOR_ALIASES, self.ebook_filename_template)
            temp_ebook.open_metadata()
            if not temp_ebook.metadata.is_complete:
                print(" -> skipping ebook with incomplete metadata: ",  ebook )
                continue

            # check if book not already in library
            already_in_db = False
            for eb in self.ebooks:
                if eb.metadata.author == temp_ebook.metadata.author and eb.metadata.title == temp_ebook.metadata.title:
                    already_in_db = True
                    break
            if already_in_db:
                print(" -> library already contains an entry for: ", temp_ebook.metadata.author, " - ", temp_ebook.metadata.title, ": ",  ebook )
                continue

            if self.interactive:
                print("About to import: %s"%str(temp_ebook) )
                answer = input("Confirm? \ny/n? ")
                if answer.lower() == "n":
                    print(" -> skipping ebook ",  ebook )
                    continue

            # if all checks are ok, importing
            print(" ->",  ebook )
            # backup
            if self.backup_imported_ebooks:
                # backup original mobi version if it exists
                if os.path.exists(ebook_candidate_full_path.replace(".epub", ".mobi")):
                    shutil.move( ebook_candidate_full_path.replace(".epub", ".mobi"), os.path.join(IMPORTED_DIR, ebook.replace(".epub", ".mobi") ) )
                shutil.copyfile( ebook_candidate_full_path, os.path.join(IMPORTED_DIR, ebook ) )
            # import
            shutil.move( ebook_candidate_full_path, os.path.join(LIBRARY_DIR, ebook))
            imported_count +=1
        print("Imported ebooks in %.2fs."%(time.perf_counter() - start))

        if imported_count != 0:
            return True
        else:
            return False

    def update_kindle_collections(self, outfile, filtered = []):
        # generates the json file that is used
        # by the kual script in librariansync/
        #print("Building kindle collections from tags.")
        if filtered == []:
            ebooks_to_sync = self.ebooks
        else:
            ebooks_to_sync = filtered
        tags_json = {}
        for eb in sorted(ebooks_to_sync, key=lambda x: x.filename):
            if eb.tags != [""]:
                tags_json[os.path.join(KINDLE_DOCUMENTS_SUBDIR, eb.exported_filename)] = eb.tags

        f = codecs.open(outfile, "w", "utf8")
        f.write(json.dumps(tags_json, sort_keys=True, indent=2, separators=(',', ': '), ensure_ascii = False))
        f.close()

    def sync_with_kindle(self, filtered = []):
        if filtered == []:
            ebooks_to_sync = self.ebooks
        else:
            ebooks_to_sync = filtered

        print("Syncing with kindle.")
        if not os.path.exists(KINDLE_ROOT):
            print("Kindle is not connected/mounted. Abandon ship.")
            return
        if not os.path.exists(KINDLE_DOCUMENTS):
            os.makedirs(KINDLE_DOCUMENTS)

        start = time.perf_counter()
        # list all mobi files in KINDLE_DOCUMENTS
        print(" -> Listing existing ebooks.")
        all_mobi_ebooks = []
        for root, dirs, files in os.walk(KINDLE_DOCUMENTS):
            all_mobi_ebooks.extend( [os.path.join(root, file) for file in files if os.path.splitext(file)[1] == ".mobi"] )

        # sync books / convert to mobi
        print(" -> Syncing library.")
        cpt = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers = multiprocessing.cpu_count()) as executor:
            all_sync = { executor.submit(eb.sync_with_kindle, KINDLE_DIR, KINDLE_DOCUMENTS): eb for eb in sorted(ebooks_to_sync, key=lambda x: x.filename)}
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
        # remove empty dirs in KINDLE_DOCUMENTS
        for root, dirs, files in os.walk(KINDLE_DOCUMENTS, topdown=False):
            for dir in [os.path.join(root, el) for el in dirs if os.listdir( os.path.join(root, el)) == []]:
                os.rmdir(dir)

        # sync collections.json
        print(" -> Generating and copying database for collection generation.")
        self.update_kindle_collections(COLLECTIONS, filtered)
        shutil.copy(COLLECTIONS, KINDLE_EXTENSIONS)
        print("Library synced to kindle in %.2fs."%(time.perf_counter() - start))

    def list_incomplete_metadata(self):
        found_incomplete = False
        incomplete_list = ""
        for eb in self.ebooks:
            if not eb.metadata.is_complete:
                found_incomplete = True
                incomplete_list += " -> %s\n"%eb.path
        if found_incomplete:
            print("The following ebooks have incomplete metadata:")
            print(incomplete_list)
        return found_incomplete

if __name__ == "__main__":

    start = time.perf_counter()

    parser = argparse.ArgumentParser(description='Librarian. A very early version of it.')

    group_import_export = parser.add_argument_group('Library management', 'Import, analyze, and sync with Kindle.')
    group_import_export.add_argument('-i', '--import',      dest='import_ebooks',   action='store_true', default = False, help='import ebooks')
    group_import_export.add_argument('-r', '--refresh',     dest='refresh',         action='store_true', default = False, help='refresh library')
    group_import_export.add_argument('-s', '--scrape',      dest='scrape',          action='store_true', default = False, help='scrape for ebooks')
    group_import_export.add_argument('-k', '--sync-kindle', dest='kindle',          action='store_true', default = False, help='sync library (or a subset with --filter or --list) with kindle')

    group_tagging = parser.add_argument_group('Tagging', 'Search and tag ebooks. For --list, --filter and --exclude, \
                                              STRING can begin with author:, title:, tag:, series: or progress: for a more precise search.')
    group_tagging.add_argument('-f', '--filter',        dest='filter_ebooks_and',   action='store', nargs="*", metavar="STRING",                help='list ebooks in library matching ALL patterns')
    group_tagging.add_argument('-l', '--list',          dest='filter_ebooks_or',    action='store', nargs="*", metavar="STRING",                help='list ebooks in library matching ANY pattern')
    group_tagging.add_argument('-x', '--exclude',       dest='filter_exclude',      action='store', nargs="+", metavar="STRING",                help='exclude ALL STRINGS from current list/filter')
    group_tagging.add_argument('-t', '--add-tag',       dest='add_tag',             action='store', nargs="+", metavar="TAG",                   help='tag listed ebooks in library')
    group_tagging.add_argument('-d', '--delete-tag',    dest='delete_tag',          action='store', nargs="+", metavar="TAG",                   help='remove tag(s) from listed ebooks in library')
    group_tagging.add_argument('-c', '--collections',   dest='collections',         action='store', nargs='?', metavar="COLLECTION", const="",  help='list all tags or ebooks with a given tag or "untagged"')
    group_tagging.add_argument(      '--progress',      dest='read',                choices = ['read', 'reading', 'not_read'],                  help='Set filtered ebooks as read.')


    group_tagging = parser.add_argument_group('Metadata', 'Display and write epub metadata.')
    group_tagging.add_argument('--info',            dest='info',            action='store',       metavar="METADATA_FIELD",           nargs='*',  help='Display all or a selection of metadata tags for filtered ebooks.')
    group_tagging.add_argument('--openlibrary',     dest='openlibrary',     action='store_true',  default = False,                                help='Search OpenLibrary for filtered ebooks.')
    group_tagging.add_argument('--write-metadata',  dest='write_metadata',  action='store',       metavar="METADATA_FIELD_AND_VALUE", nargs='+',  help='Write one or several field:value metadata.')


    group_tagging = parser.add_argument_group('Configuration', 'Configuration options.')
    group_tagging.add_argument('--config', dest='config', action='store', metavar="CONFIG_FILE", nargs=1, help='Use an alternative configuration file.')

    args = parser.parse_args()

    # a few checks on the arguments
    if not len(sys.argv) > 1:
        print("No option selected. Try -h.")
        sys.exit()

    is_not_filtered = (args.filter_ebooks_and is None and args.filter_ebooks_or is None)
    if is_not_filtered and (args.filter_exclude is not None or args.info is not None) :
        print("The --exclude/--info options can only be used with either --list or --filter.")
        sys.exit()
    if (args.add_tag is not None or args.delete_tag is not None) and (args.filter_ebooks_and is None or args.filter_ebooks_and == []) and (args.filter_ebooks_or is None or args.filter_ebooks_or == []) :
        print("Tagging all ebooks, or removing a tag from all ebooks, arguably makes no sense. Use the --list/--filter options to filter among the library.")
        sys.exit()

    if args.config is not None:
        config_filename = args.config[0]
        if os.path.isabs(config_filename):
            if os.path.exists(config_filename):
                LIBRARY_CONFIG = config_filename
        else:
            config_filename = os.path.join(librarian_dir, config_filename)
            if os.path.exists(config_filename):
                LIBRARY_CONFIG = config_filename


    with Library() as l:
        try:
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

            # filtering
            filtered = []
            s = EbookSearch(l.ebooks)
            if args.collections is not None:
                if args.collections == "":
                    all_tags = s.list_tags()
                    for tag in sorted(all_tags.keys()):
                        print(" -> %s (%s)"%(tag, all_tags[tag]))
                elif args.collections == "untagged":
                    filtered = s.search([""], ["tag:"], additive = False)
                else:
                    filtered = s.search_ebooks('tag:%s'%args.collections, exact_search = True)

            if args.filter_ebooks_and is not None:
                filtered = s.search(args.filter_ebooks_and, args.filter_exclude, additive = True)
            elif args.filter_ebooks_or is not None:
                filtered = s.search(args.filter_ebooks_or, args.filter_exclude, additive = False)

            # add/remove tags
            if args.add_tag is not None and filtered != []:
                for ebook in filtered:
                    for tag in args.add_tag:
                        ebook.add_to_collection(tag)
            if args.delete_tag is not None and filtered != []:
                for ebook in filtered:
                    for tag in args.delete_tag:
                        ebook.remove_from_collection(tag)

            #print('(', read("read"), not_read("not_read"), reading("reading"), ')')
            for ebook in filtered:

                if args.info is None:
                    print(" -> ", ebook)
                    if args.openlibrary:
                        s = OpenLibrarySearch()
                        s.search(ebook)
                else:
                    if args.info == []:
                        print(ebook.info())
                    else:
                        print(ebook.info(args.info))

                if args.write_metadata is not None:
                    ebook.update_metadata(args.write_metadata)

                if args.read is not None:
                    ebook.set_progress(args.read)


            if args.kindle:
                if filtered == []:
                    l.sync_with_kindle()
                else:
                    l.sync_with_kindle(filtered)

            l.save_db()
        except Exception as err:
            print(err)
            sys.exit(-1)

        print("Everything done in %.2fs."%(time.perf_counter() - start))
