#!/usr/bin/env python
"""
Create directory listing with md5 for github pages
"""

import os
import hashlib

def create_md5(fname):
    md5_file = fname + ".md5"
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    md5 = hash_md5.hexdigest()
    print("write md5 file for %s to %s" % (fname, md5_file))
    with open(md5_file, 'w') as f:
        f.write(md5)


parent_folder = './'
all_dirs = []
for dir_name in os.listdir(parent_folder):
    subdir = os.path.join(parent_folder, dir_name)
    if os.path.isdir(subdir) and dir_name not in [".git", "externals"]:
        # addon directory
        all_dirs.append(dir_name)
        html = "<html>\n<body>\n<h1>Directory listing for %s</h1>\n<hr/>\n<pre>" % dir_name
        html += "<a href=\"../index.html\">..</a>\n"
        for filename in os.listdir(subdir):
            if filename.endswith(".zip"):
                file = os.path.join(subdir, filename)
                # create md5 hash
                create_md5(file)
                # append zip to html listing
                html += "<a href=\"%s\">%s</a>\n" % (filename, filename)
                md5_file = filename + ".md5"
                html += "<a href=\"%s\">%s</a>\n" % (md5_file, md5_file)
        html += "</pre>\n</body>\n</html>"
        html_file = os.path.join(subdir, "index.html")
        print ("write html file %s" % html_file)
        with open(html_file, 'w') as f:
            f.write(html)

# write main index.html
html = "<html>\n<body>\n<h1>Directory listing</h1>\n<hr/>\n<pre>"
for dir_name in all_dirs:
    dir_path = os.path.join(parent_folder, dir_name, 'index.html')
    html += "<a href=\"%s\">%s</a>\n" % (dir_path, dir_name)
html += "</pre>\n</body>\n</html>"
html_file = os.path.join(parent_folder, "index.html")
print ("write html file %s" % html_file)
with open(html_file, 'w') as f:
    f.write(html)





