#!/usr/bin/env python
r"""
Create a Kodi add-on repository from add-on sources

This tool extracts Kodi add-ons from their respective locations and
copies the appropriate files into a Kodi add-on repository. Each add-on
is placed in its own directory. Each contains the add-on metadata files
and a zip archive. In addition, the repository catalog "addons.xml" is
placed in the repository folder.

This script has been tested with Python 2.7.6 and Python 3.4.3. It
depends on the GitPython module.

Based on the original script by Chad Perry <github@chad.parry.org> 
"""

__author__ = "Marcel van der Veldt"
__contact__ = "vanderveldtmarcel@gmail.com"
__copyright__ = "Copyright 2016 Chad Parry, Copyright 2018 Marcel van der Veldt"
__license__ = "GNU GENERAL PUBLIC LICENSE. Version 2, June 1991"
__version__ = "1.2.2"


import argparse
import collections
import gzip
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import threading
import xml.etree.ElementTree
import zipfile
import time
from traceback import format_exc
import platform
import subprocess

AddonMetadata = collections.namedtuple(
    'AddonMetadata', ('id', 'version', 'root'))
WorkerResult = collections.namedtuple(
    'WorkerResult', ('addon_metadata', 'exc_info'))
AddonWorker = collections.namedtuple('AddonWorker', ('thread', 'result_slot'))


INFO_BASENAME = 'addon.xml'
METADATA_BASENAMES = (
    INFO_BASENAME,
    'icon.png',
    'fanart.jpg')


def get_archive_basename(addon_metadata):
    return '{}-{}.zip'.format(addon_metadata.id, addon_metadata.version)


def get_metadata_basenames(addon_metadata):
    return ([(basename, basename) for basename in METADATA_BASENAMES] +
            [(
                'changelog.txt',
                'changelog-{}.txt'.format(addon_metadata.version))])


def is_url(addon_location):
    return bool(re.match('[A-Za-z0-9+.-]+://.', addon_location))


def parse_metadata(metadata_file):
    # Parse the addon.xml metadata.
    tree = xml.etree.ElementTree.parse(metadata_file)
    root = tree.getroot()
    addon_metadata = AddonMetadata(
        root.get('id'),
        root.get('version'),
        root)
    # Validate the add-on ID.
    if (addon_metadata.id is None or
            re.search('[^a-z0-9._-]', addon_metadata.id)):
        raise RuntimeError('Invalid addon ID: ' + str(addon_metadata.id))
    if (addon_metadata.version is None or
            not re.match(r'\d+\.\d+\.\d+$', addon_metadata.version)):
        raise RuntimeError(
            'Invalid addon verson: ' + str(addon_metadata.version))
    return addon_metadata


def copy_metadata_files(source_folder, addon_target_folder, addon_metadata):
    for (source_basename, target_basename) in get_metadata_basenames(
            addon_metadata):
        source_path = os.path.join(source_folder, source_basename)
        if os.path.isfile(source_path):
            shutil.copyfile(
                source_path,
                os.path.join(addon_target_folder, target_basename))


def fetch_addon_from_git(addon_location, target_folder, temp_folder):
    alt_addonid = ""
    alt_addonname = ""
    git_branch = "master"
    addon_vars = addon_location.split("#")
    git_location = addon_vars[0]
    if len(addon_vars) > 1:
        git_branch = addon_vars[1]
    if len(addon_vars) > 2:
        alt_addonid = addon_vars[2]
    if len(addon_vars) > 3:
        alt_addonname = addon_vars[3]
        
    download_url = git_location + "/archive/%s.zip" % git_branch
    addon_id = git_location.split("/")[-1]
        
    zip_file = os.path.join(temp_folder, "%s%s.zip" %(addon_id,alt_addonid))
    zip_file = os.path.abspath(zip_file)    
    
    #download zip file for addon
    import requests
    response = requests.get(download_url, stream=True)
    with open(zip_file, 'wb') as out_file:
        shutil.copyfileobj(response.raw, out_file)
    del response

    #unzip
    addon_temp = os.path.join(temp_folder,addon_id + alt_addonid)
    addon_temp = os.path.abspath(addon_temp)
    os.makedirs(addon_temp)
    do_unzip(zip_file, addon_temp)
    addon_temp = os.path.join(addon_temp, "%s-%s" %(addon_id, git_branch) )
    
    #if alt addonid is given, change the addonid (used for beta skin versions)
    if alt_addonid and alt_addonname:
        addon_file = os.path.join(addon_temp, "addon.xml")
        f = open(addon_file,'r')
        filedata = f.read()
        f.close()

        newdata = filedata.replace(addon_id, alt_addonid)
        body = newdata.replace('\r', '').replace('\n', '').replace('\t', '')
        addon_name = re.compile('name="(.*?)"').findall(body)[0]
        newdata = newdata.replace(addon_name, alt_addonname)
        f = open(addon_file,'w')
        f.write(newdata)
        f.close()
        
    
    #proceed with lookup from folder
    addon_metadata = fetch_addon_from_folder(addon_temp, target_folder)
    
    return addon_metadata

   
def fetch_addon_from_folder(raw_addon_location, target_folder):
    try:
        addon_location = os.path.abspath(raw_addon_location)
        metadata_path = os.path.join(addon_location, INFO_BASENAME)
        addon_metadata = parse_metadata(metadata_path)
        addon_target_folder = os.path.join(target_folder, addon_metadata.id)
        
        #check current version
        cur_metadata_path = os.path.join(addon_target_folder, INFO_BASENAME)
        if os.path.exists(cur_metadata_path):
            cur_metadata = parse_metadata(cur_metadata_path)
            if cur_metadata.version == addon_metadata.version:
                print "Addon %s already has version %s on the repo, skipping..." % (addon_metadata.id, addon_metadata.version)
                return cur_metadata
        
        #if skin addon, build textures...
        if addon_metadata.id.startswith("skin."):
            buildskintextures(raw_addon_location)

        # Create the compressed add-on archive.
        if not os.path.isdir(addon_target_folder):
            os.mkdir(addon_target_folder)
        archive_path = os.path.join(
            addon_target_folder, get_archive_basename(addon_metadata))
    
        with zipfile.ZipFile(
                archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for (root, dirs, files) in os.walk(addon_location.decode("utf-8")):
                relative_root = os.path.join(
                    addon_metadata.id,
                    os.path.relpath(root, addon_location))
                for relative_path in files:
                    sourcefile = os.path.join(root, relative_path)
                    destfile = os.path.join(relative_root, relative_path)
                    archive.write(sourcefile, destfile)
                    
        copy_metadata_files(
            addon_location, addon_target_folder, addon_metadata)

    except Exception as exc:
        print format_exc(sys.exc_info())
        raise exc
        
    return addon_metadata
    
def buildskintextures(addon_folder):
    #build skin media files and themes with texturepacker
    themes_dir = os.path.join(addon_folder, "themes")
    media_dir = os.path.join(addon_folder, "media")
    if os.path.isdir(media_dir):
        if not os.path.isdir(themes_dir):
            os.mkdir(themes_dir)
        #move existing media folder to themes dir
        shutil.move(media_dir, os.path.join(themes_dir, "Textures"))
        #recreate empty media dir
        os.makedirs(media_dir)
        for item in os.listdir(themes_dir):
            themedir = os.path.join(themes_dir, item)
            if os.path.isdir(themedir):
                theme_file = os.path.join(media_dir, "%s.xbt" % item)
                tpargs = '-dupecheck -input %s -output %s' %(themedir, theme_file)
                if "Windows" in platform.platform():
                    subprocess.Popen( ('externals/texturepacker/windows/TexturePacker.exe', tpargs )).wait()
                elif "Darwin" in platform.platform():
                    subprocess.Popen( ('externals/texturepacker/macos/TexturePacker', tpargs )).wait()
                else:
                    cmd = "externals/texturepacker/linux/TexturePacker %s" % tpargs
                    subprocess.Popen(cmd, shell=True).wait()
        #remove themes dir
        shutil.rmtree(themes_dir, ignore_errors=False)
    
def samefile(file1, file2):
    return os.stat(file1) == os.stat(file2)

def fetch_addon_from_zip(raw_addon_location, target_folder):
    addon_location = os.path.abspath(raw_addon_location)
    with zipfile.ZipFile(
            addon_location, compression=zipfile.ZIP_DEFLATED) as archive:
        # Find out the name of the archive's root folder.
        roots = frozenset(
            next(iter(path.split(os.path.sep)), '')
            for path in archive.namelist())
        if len(roots) != 1:
            raise RuntimeError('Archive should contain one directory')
        root = next(iter(roots))
        if not root:
            raise RuntimeError('Archive should contain a directory')

        metadata_file = archive.open(os.path.join(root, INFO_BASENAME))
        addon_metadata = parse_metadata(metadata_file)
        addon_target_folder = os.path.join(target_folder, addon_metadata.id)

        # Copy the metadata files.
        if not os.path.isdir(addon_target_folder):
            os.mkdir(addon_target_folder)
        for (source_basename, target_basename) in get_metadata_basenames(
                addon_metadata):
            try:
                source_file = archive.open(os.path.join(root, source_basename))
            except KeyError:
                continue
            with open(
                    os.path.join(addon_target_folder, target_basename),
                    'wb') as target_file:
                shutil.copyfileobj(source_file, target_file)

    # Copy the archive.
    archive_basename = get_archive_basename(addon_metadata)
    archive_path = os.path.join(addon_target_folder, archive_basename)
    if (not samefile(
            os.path.dirname(addon_location), addon_target_folder) or
            os.path.basename(addon_location) != archive_basename):
        shutil.copyfile(addon_location, archive_path)

    return addon_metadata
   
def do_unzip(zip_path, targetdir):
    zip_file = zipfile.ZipFile(zip_path, 'r', allowZip64=True)
    for fileinfo in zip_file.infolist():
        #filename = fileinfo.filename
        filename = fileinfo.filename
        if not filename.endswith("/"):
            cur_path = os.path.join(targetdir, filename)
            basedir = os.path.dirname(cur_path)
            if not os.path.isdir(basedir):
                os.makedirs(basedir)
            #use shutil to support non-ascii formatted files in the zip
            outputfile = open(cur_path, "wb")
            shutil.copyfileobj(zip_file.open(fileinfo.filename), outputfile)
            outputfile.close()
    zip_file.close()
    print "UNZIP DONE of file %s" %(zip_path)
    
def fetch_addon(addon_location, target_folder, result_slot, temp_folder):
    try:
        print "Processing %s" %addon_location
        if is_url(addon_location):
            addon_metadata = fetch_addon_from_git(
                addon_location, target_folder, temp_folder)
        elif os.path.isdir(addon_location):
            addon_metadata = fetch_addon_from_folder(
                addon_location, target_folder)
        elif os.path.isfile(addon_location):
            addon_metadata = fetch_addon_from_zip(
                addon_location, target_folder)
        else:
            raise RuntimeError('Path not found: ' + addon_location)
        result_slot.append(WorkerResult(addon_metadata, None))
    except:
        result_slot.append(WorkerResult(None, sys.exc_info()))


def get_addon_worker(addon_location, target_folder, temp_folder):
    result_slot = []
    thread = threading.Thread(target=lambda: fetch_addon(
        addon_location, target_folder, result_slot, temp_folder))
    return AddonWorker(thread, result_slot)

def cleanup_dir(dirname):
    #cleanup directory from disk
    if "Windows" in platform.platform():
        cmd = 'cmd'
        cmdargs = '/c rd /s /q %s' % dirname
        subprocess.Popen( (cmd, cmdargs )).wait()
    else:
        cmd = 'rm -Rf %s' % dirname
        subprocess.Popen( cmd, shell=True).wait()
    
    while os.path.isdir(dirname):
        print "wait for folder deletion"
        time.sleep(1)

    
def create_repository(
        addon_locations,
        target_folder,
        info_path,
        checksum_path,
        is_compressed):
    
    # Import git lazily.
    if any(is_url(addon_location) for addon_location in addon_locations):
        try:
            global git
            import git
        except ImportError:
            raise RuntimeError(
                'Please install GitPython: pip install gitpython')
    # Create the target folder.
    if not os.path.isdir(target_folder):
        os.mkdir(target_folder)
        
    # create temp folder
    #data_path = os.path.abspath(args.datadir)
   
    temp_folder = os.path.abspath(os.path.join(target_folder, "temp"))
    cleanup_dir(temp_folder)
    if not os.path.isdir(temp_folder):
        os.makedirs(temp_folder)

    # Fetch all the add-on sources in parallel.
    workers = [
        get_addon_worker(addon_location, target_folder, temp_folder)
        for addon_location in addon_locations]
    for worker in workers:
        worker.thread.start()
    for worker in workers:
        worker.thread.join()

    # Collect the results from all the threads.
    metadata = []
    for worker in workers:
        try:
            result = next(iter(worker.result_slot))
        except StopIteration:
            raise RuntimeError('Addon worker did not report result')
        if result.exc_info is not None:
            raise result.exc_info[1]
        metadata.append(result.addon_metadata)

    # Generate the addons.xml file.
    root = xml.etree.ElementTree.Element('addons')
    for addon_metadata in metadata:
        root.append(addon_metadata.root)
    tree = xml.etree.ElementTree.ElementTree(root)
    with io.BytesIO() as info_file:
        tree.write(info_file, encoding='UTF-8', xml_declaration=True)
        info_contents = info_file.getvalue()

    if is_compressed:
        info_file = gzip.open(info_path, 'wb')
    else:
        info_file = open(info_path, 'wb')
    with info_file:
        info_file.write(info_contents)

    # Calculate the signature.
    digest = hashlib.md5(info_contents).hexdigest()
    with open(checksum_path, 'w') as sig:
        sig.write(digest)
        
    #cleanup temp files
    cleanup_dir(temp_folder)

def main():
    parser = argparse.ArgumentParser(
        description='Create a Kodi add-on repository from add-on sources')
    parser.add_argument(
        '--datadir',
        '-d',
        default='.',
        help='Path to place the add-ons [current directory]')
    parser.add_argument(
        '--info',
        '-i',
        help='''Path for the addons.xml file [DATADIR/addons.xml or
                DATADIR/addons.xml.gz if compressed]''')
    parser.add_argument(
        '--checksum',
        '-c',
        help='Path for the addons.xml.md5 file [DATADIR/addons.xml.md5]')
    parser.add_argument(
        '--compressed',
        '-z',
        action='store_true',
        help='Compress addons.xml with gzip')
    parser.add_argument(
        'addon',
        nargs='*',
        metavar='ADDON',
        help='''Location of the add-on: either a path to a local folder or
                to a zip archive or a URL for a Git repository with the
                format REPOSITORY_URL#BRANCH:PATH''')
    
    #read addons to include from addonslist.txt file
    args = parser.parse_args()
    if os.path.exists("addonslist.txt"):
        with open("addonslist.txt") as f:
            for line in f.readlines():
                if not line.startswith("#"):
                    args.addon.append(line.strip('\n').strip('\t'))

    data_path = os.path.abspath(args.datadir)
    if args.info is None:
        if args.compressed:
            info_basename = 'addons.xml.gz'
        else:
            info_basename = 'addons.xml'
        info_path = os.path.join(data_path, info_basename)
    else:
        info_path = os.path.abspath(args.info)

    checksum_path = (
        os.path.abspath(args.checksum) if args.checksum is not None
        else os.path.join(data_path, 'addons.xml.md5'))
    create_repository(
        args.addon, data_path, info_path, checksum_path, args.compressed)


if __name__ == "__main__":
    main()
