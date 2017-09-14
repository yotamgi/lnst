"""

Copyright 2012 Red Hat, Inc.
Licensed under the GNU General Public License, version 2 as
published by the Free Software Foundation; see COPYING for details.
"""

__author__ = """
rpazdera@redhat.com (Radek Pazdera)
"""

import logging
import os
import re
import time
import shutil
from lnst.Common.ExecCmd import exec_cmd

SETUP_SCRIPT_NAME = "lnst-setup.sh"

class ResourceCacheError(Exception):
    pass

class ResourceCache(object):
    _CACHE_INDEX_FILE_NAME = "index"
    _root = None
    _entries = {}
    _expiration_period = None

    def __init__(self, cache_path, expiration_period):
        if os.path.exists(cache_path):
            if os.path.isdir(cache_path):
                self._root = cache_path
            else:
                raise ResourceCacheError("Invalid cache path (%s)" % cache_path)
        else:
            os.makedirs(cache_path)
            self._root = cache_path

        self._read_index()
        self._expiration_period = expiration_period

    def _read_index(self):
        logging.debug("Test cache index loaded")
        try:
            f = open(self._get_index_loc(), "r")
        except:
            return

        for line in f.readlines():
            if not re.match("^\s*#", line) and not re.match("^\s*$", line):
                try:
                    entry_hash, last_used, entry_type, \
                    entry_name, entry_path = line.split()
                except:
                    raise ResourceCacheError("Malformed cache index")

                entry = {"type": entry_type, "name": entry_name,
                         "last_used": int(last_used), "path": entry_path }
                self._entries[entry_hash] = entry

    def _save_index(self):
        logging.debug("Test cache index commited")
        with open(self._get_index_loc(), "w") as f:
            header = "# hash                           " \
                     "last_used  type   name         path\n"
            f.write(header)
            for entry_hash, entry in self._entries.iteritems():
                values = (entry_hash, entry["last_used"], entry["type"],
                            entry["name"], entry["path"])
                line = "%s %d %s %s %s\n" % values
                f.write(line)

    def _get_index_loc(self):
        return "%s/%s" % (self._root, self._CACHE_INDEX_FILE_NAME)

    def query(self, res_hash):
        return res_hash in self._entries

    def get_path(self, res_hash):
        return "%s/%s" % (self._root, self._entries[res_hash]["path"])

    def renew_entry(self, entry_hash):
        self._entries[entry_hash]["last_used"] = int(time.time())
        self._save_index()

    def add_cache_entry(self, entry_hash, filepath, entry_name, entry_type):
        if entry_hash in self._entries:
            raise ResourceCacheError("File already in cache")

        entry_dir = "%s/%s" % (self._root, entry_hash)
        if os.path.exists(entry_dir):
            try:
                shutil.rmtree(entry_dir)
            except OSError as e:
                if e.errno != 2:
                    raise
        os.makedirs(entry_dir)

        shutil.move(filepath, entry_dir)
        entry_path = "%s/%s" % (entry_dir, os.path.basename(filepath))

        if entry_type == "module":
            filename = "%s.py" % entry_name
            shutil.move(entry_path, "%s/%s" % (entry_dir, filename))
        elif entry_type == "tools":
            filename = entry_name
            tools_dir = "%s/%s" % (entry_dir, filename)

            exec_cmd("tar xjmf \"%s\" -C \"%s\"" % (entry_path, entry_dir))

            if os.path.exists("%s/%s" % (tools_dir, SETUP_SCRIPT_NAME)):
                exec_cmd("cd \"%s\" && ./%s" % (tools_dir, SETUP_SCRIPT_NAME))
            else:
                msg = "%s not found in %s tools, skipping initialization." % \
                           (SETUP_SCRIPT_NAME, entry_name)
                logging.warn(msg)

        entry = {"type": entry_type, "name": entry_name,
                 "last_used": int(time.time()),
                 "path": "%s/%s" % (entry_hash, filename)}
        self._entries[entry_hash] = entry

        self._save_index()

        return entry_hash

    def del_cache_entry(self, entry_hash):
        if entry_hash in self._entries:
            try:
                shutil.rmtree("%s/%s" % (self._root, entry_hash))
            except OSError as e:
                if e.errno != 2:
                    raise
            del self._entries[entry_hash]
            self._save_index()

    def del_old_entries(self):
        if self._expiration_period == 0:
            return

        rm = []
        now = time.time()
        for entry_hash, entry in self._entries.iteritems():
            if entry["last_used"] <= (now - self._expiration_period):
                rm.append(entry_hash)

        for entry_hash in rm:
            self.del_cache_entry(entry_hash)
