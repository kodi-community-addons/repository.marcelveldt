#!/usr/bin/python
# -*- coding: utf-8 -*-

'''get metadata and artwork for music'''

from utils import log_msg, extend_dict, get_clean_image, ADDON_ID, DialogSelect, strip_newlines
from simplecache import SimpleCache, use_cache
from mbrainz import MusicBrainz
from lastfm import LastFM
from theaudiodb import TheAudioDb
import os
import xbmc
import xbmcvfs
import xbmcgui
from urllib import quote_plus
from datetime import timedelta
from difflib import SequenceMatcher as SM


class MusicArtwork(object):
    '''get metadata and artwork for music'''

    def __init__(self, artutils=None):
        '''Initialize - optionaly provide our base ArtUtils class'''
        if not artutils:
            from artutils import ArtUtils
            self.artutils = ArtUtils
        else:
            self.artutils = artutils
        self.cache = self.artutils.cache
        self.lastfm = LastFM()
        self.mb = MusicBrainz()
        self.audiodb = TheAudioDb()

    def get_music_artwork(self, artist, album, track, disc, ignore_cache=False):
        '''get music metadata by providing artist and/or track'''
        if artist == track or album == track:
            track = ""
        artist = artist.split(" / ")[0]
        artist = artist.split("/")[0]
        details = self.get_artist_metadata(artist, album, track, ignore_cache=ignore_cache)
        if album or track:
            album_details = self.get_album_metadata(artist, album, track, disc, ignore_cache=ignore_cache)
            if details.get("plot") and album_details.get("plot"):
                details["plot"] = "%s  --  %s" % (album_details["plot"], details["plot"])
                extend_dict(details, album_details)
        return details

    def manual_set_music_artwork(self, artist, album, track, disc):
        '''manual override artwork options'''

        if album:
            artwork = self.get_album_metadata(artist, album, track, disc)
            art_types = ["thumb", "discart"]
        else:
            artwork = self.get_artist_metadata(artist, album, track)
            art_types = ["thumb", "poster", "fanart", "banner", "clearart", "clearlogo", "landscape"]
        cache_str = artwork["cachestr"]

        # show dialogselect with all artwork options
        abort = False
        while not abort:
            listitems = []
            for arttype in art_types:
                listitem = xbmcgui.ListItem(label=arttype, iconImage=artwork["art"].get(arttype, ""))
                listitem.setProperty("icon", artwork["art"].get(arttype, ""))
                listitems.append(listitem)
            dialog = DialogSelect("DialogSelect.xml", "", listing=listitems,
                             window_title=xbmc.getLocalizedString(13511), multiselect=False)
            dialog.doModal()
            selected_item = dialog.result
            del dialog
            if selected_item == -1:
                abort = True
            else:
                # show results for selected art type
                artoptions = []
                selected_item = listitems[selected_item]
                image = selected_item.getProperty("icon")
                label = selected_item.getLabel()
                heading = "%s: %s" % (xbmc.getLocalizedString(13511), label)
                if image:
                    # current image
                    listitem = xbmcgui.ListItem(label=xbmc.getLocalizedString(13512), iconImage=image, label2=image)
                    listitem.setProperty("icon", image)
                    artoptions.append(listitem)
                    # none option
                    listitem = xbmcgui.ListItem(label=xbmc.getLocalizedString(231), iconImage="DefaultAddonNone.png")
                    listitem.setProperty("icon", "DefaultAddonNone.png")
                    artoptions.append(listitem)
                # browse option
                listitem = xbmcgui.ListItem(label=xbmc.getLocalizedString(1024), iconImage="DefaultFolder.png")
                listitem.setProperty("icon", "DefaultFolder.png")
                artoptions.append(listitem)

                # add remaining images as option
                allarts = artwork["art"].get(label + "s", [])
                if len(allarts) > 1:
                    for item in allarts:
                        listitem = xbmcgui.ListItem(label=item, iconImage=item)
                        listitem.setProperty("icon", item)
                        artoptions.append(listitem)

                w2 = DialogSelect("DialogSelect.xml", "", listing=artoptions, window_title=heading)
                w2.doModal()
                selected_item = w2.result
                del w2
                if image and selected_item == 1:
                    artwork["art"][label] = ""
                elif image and selected_item > 2:
                    artwork["art"][label] = artoptions[selected_item].getProperty("icon")
                elif (image and selected_item == 2) or not image and selected_item == 0:
                    # manual browse...
                    dialog = xbmcgui.Dialog()
                    image = dialog.browse(2, xbmc.getLocalizedString(1030),
                                          'files', mask='.gif|.png|.jpg').decode("utf-8")
                    del dialog
                    if image:
                        artwork["art"][label] = image

        # save results in cache
        self.artutils.cache.set(cache_str, artwork, expiration=timedelta(days=120))

    def music_artwork_options(self, artist, album, track, disc):
        '''show options for music artwork'''
        options = []
        options.append(self.artutils.addon.getLocalizedString(32028))  # Refresh item (auto lookup)
        options.append(self.artutils.addon.getLocalizedString(32036))  # Choose art
        options.append(self.artutils.addon.getLocalizedString(32034))  # Open addon settings
        header = self.artutils.addon.getLocalizedString(32015)
        dialog = xbmcgui.Dialog()
        ret = dialog.select(header, options)
        del dialog
        if ret == 0:
            # Refresh item (auto lookup)
            self.artutils.fanarttv.ignore_cache = True
            self.audiodb.ignore_cache = True
            self.mb.ignore_cache = True
            self.lastfm.ignore_cache = True
            self.get_music_artwork(artist, album, track, disc, ignore_cache=True)
        elif ret == 1:
            # Choose art
            self.manual_set_music_artwork(artist, album, track, disc)
        elif ret == 2:
            # Open addon settings
            xbmc.executebuiltin("Addon.OpenSettings(%s)" % ADDON_ID)

    def get_artist_metadata(self, artist, album, track, ignore_cache=False):
        '''collect all artist metadata'''

        cache_str = "music_artwork.artist.%s" % artist.lower()
        cache = self.artutils.cache.get(cache_str)
        if cache and not ignore_cache:
            return cache

        log_msg("get_artist_metadata --> artist: %s - album: %s - track: %s" % (artist, album, track))

        details = {"art": {}}
        details["cachestr"] = cache_str
        local_path = ""
        local_path_custom = ""
        # get metadata from kodi db
        extend_dict(details, self.get_artist_kodi_metadata(artist, album, track))
        # get artwork from songlevel path
        if details.get("diskpath") and self.artutils.addon.getSetting("music_art_musicfolders") == "true":
            extend_dict(details["art"], self.lookup_artistart_in_folder(details["diskpath"]))
            local_path = details["diskpath"]
        # get artwork from custom folder
        if self.artutils.addon.getSetting("music_art_custom") == "true":
            custom_path = self.artutils.addon.getSetting("music_art_custom_path").decode("utf-8")
            if custom_path:
                diskpath = self.get_customfolder_path(custom_path, artist)
                if diskpath:
                    extend_dict(details["art"], self.lookup_artistart_in_folder(diskpath))
                    local_path_custom = diskpath
        # lookup online metadata
        if self.artutils.addon.getSetting("music_art_scraper") == "true":
            if not album and not track:
                album = details.get("ref_album")
                track = details.get("ref_track")
            mb_artistid = self.get_mb_artist_id(artist, album, track)
            if mb_artistid:
                # get artwork from fanarttv
                extend_dict(details["art"], self.artutils.fanarttv.artist(mb_artistid))
                # get metadata from theaudiodb
                extend_dict(details, self.audiodb.artist_info(mb_artistid))
                # get metadata from lastfm
                extend_dict(details, self.lastfm.artist_info(mb_artistid))

                # download artwork to music folder
                if local_path and self.artutils.addon.getSetting("music_art_download") == "true":
                    details["art"] = self.download_artwork(local_path, details["art"])
                # download artwork to custom folder
                if local_path_custom and self.artutils.addon.getSetting("music_art_download_custom") == "true":
                    details["art"] = self.download_artwork(local_path_custom, details["art"])

                # fix extrafanart
                if details["art"].get("fanarts"):
                    for count, item in enumerate(details["art"]["fanarts"]):
                        details["art"]["fanart.%s" % count] = item
                    if not details["art"].get("extrafanart") and len(details["art"]["fanarts"]) > 1:
                        details["art"]["extrafanart"] = "plugin://script.skin.helper.service/"\
                            "?action=extrafanart&fanarts=%s" % quote_plus(repr(details["art"]["fanarts"]))

        # store results in cache and return results
        self.artutils.cache.set(cache_str, details)
        return details

    def get_album_metadata(self, artist, album, track, disc, ignore_cache=False):
        '''collect all album metadata'''

        cache_str = "music_artwork.album.%s.%s.%s" % (artist.lower(), album.lower(), disc.lower())
        if not album and track:
            cache_str = "music_artwork.album.%s.%s" % (artist.lower(), track.lower())
        cache = self.artutils.cache.get(cache_str)
        if cache and not ignore_cache:
            return cache

        details = {"art": {}}
        details["cachestr"] = cache_str
        local_path = ""
        local_path_custom = ""
        # get metadata from kodi db
        extend_dict(details, self.get_album_kodi_metadata(artist, album, track, disc))
        # get artwork from songlevel path
        if details.get("diskpath") and self.artutils.addon.getSetting("music_art_musicfolders") == "true":
            extend_dict(details["art"], self.lookup_albumart_in_folder(details["diskpath"]))
            local_path = details["diskpath"]
        # get artwork from custom folder
        if self.artutils.addon.getSetting("music_art_custom") == "true":
            custom_path = self.artutils.addon.getSetting("music_art_custom_path").decode("utf-8")
            if custom_path:
                diskpath = self.get_custom_album_path(custom_path, artist, album, disc)
                if diskpath:
                    extend_dict(details["art"], self.lookup_albumart_in_folder(diskpath))
                    local_path_custom = diskpath
        # lookup online metadata
        if self.artutils.addon.getSetting("music_art_scraper") == "true":
            mb_albumid = self.get_mb_album_id(artist, album, track)
            if mb_albumid:
                # get artwork from fanarttv
                extend_dict(details["art"], self.artutils.fanarttv.album(mb_albumid))
                # get metadata from theaudiodb
                extend_dict(details, self.audiodb.album_info(mb_albumid))
                # get metadata from lastfm
                extend_dict(details, self.lastfm.album_info(mb_albumid))
                # musicbrainz thumb as last resort
                if not details["art"].get("thumb"):
                    details["art"]["thumb"] = self.mb.get_albumthumb(mb_albumid)

                # download artwork to music folder
                if local_path and self.artutils.addon.getSetting("music_art_download") == "true":
                    details["art"] = self.download_artwork(local_path, details["art"])
                # download artwork to custom folder
                if local_path_custom and self.artutils.addon.getSetting("music_art_download_custom") == "true":
                    details["art"] = self.download_artwork(local_path_custom, details["art"])

        # store results in cache and return results
        self.artutils.cache.set(cache_str, details)
        return details

    def get_artist_kodi_metadata(self, artist, album, track):
        '''get artist details from the kodi database'''
        details = {}
        filters = [{"operator": "is", "field": "artist", "value": artist}]
        result = self.artutils.kodidb.artists(filters=filters, limits=(0, 1))
        if result:
            details = result[0]
            song_path = ""
            details["title"] = details["artist"]
            details["plot"] = strip_newlines(details["description"])
            filters = [{"artistid": details["artistid"]}]
            artist_albums = self.artutils.kodidb.albums(filters=filters)
            details["albums"] = []
            for item in artist_albums:
                details["albums"].append(item["label"])
                if not song_path:
                    # retrieve path on disk by selecting one song for this artist
                    filters = [{"albumid": item["albumid"]}]
                    album_tracks = self.artutils.kodidb.songs(filters=filters, limits=(0, 1))
                    if album_tracks:
                        song_path = album_tracks[0]["file"]
                        details["diskpath"] = self.get_artistpath_by_songpath(song_path, artist)
                        details["ref_album"] = item["title"]
                        details["ref_track"] = album_tracks[0]["title"]
            joinchar = "[CR]• ".decode("utf-8")
            details["albums.formatted"] = joinchar.join(details["albums"])
            details["art"] = {}
            fanart = get_clean_image(details["fanart"])
            if xbmcvfs.exists(fanart):
                details["art"]["fanart"] = fanart
            del details["fanart"]
            thumbnail = get_clean_image(details["thumbnail"])
            if xbmcvfs.exists(thumbnail):
                details["art"]["thumb"] = thumbnail
            del details["thumbnail"]
        return details

    def get_album_kodi_metadata(self, artist, album, track, disc):
        '''get album details from the kodi database'''
        details = {}
        filters = [{"operator": "is", "field": "album", "value": album}]
        filters.append({"operator": "is", "field": "artist", "value": artist})
        if artist and track and not album:
            # get album by track
            result = self.artutils.kodidb.songs(filters=filters)
            for item in result:
                album = result["album"]
                break
        if artist and album:
            result = self.artutils.kodidb.albums(filters=filters)
            if result:
                details = result[0]
                details["plot"] = strip_newlines(details["description"])
                filters = [{"albumid": details["albumid"]}]
                album_tracks = self.artutils.kodidb.songs(filters=filters)
                details["tracks"] = []
                for item in album_tracks:
                    details["tracks"].append(item["title"])
                    if not details.get("diskpath"):
                        if not disc or item["disc"] == int(disc):
                            details["diskpath"] = self.get_albumpath_by_songpath(item["file"])
                joinchar = "[CR]• ".decode("utf-8")
                details["tracks.formatted"] = joinchar.join(details["tracks"])
                details["art"] = {}
                fanart = get_clean_image(details["fanart"])
                if xbmcvfs.exists(fanart):
                    details["art"]["fanart"] = fanart
                del details["fanart"]
                thumbnail = get_clean_image(details["thumbnail"])
                if xbmcvfs.exists(thumbnail):
                    details["art"]["thumb"] = thumbnail
                del details["thumbnail"]
        return details

    def get_mb_artist_id(self, artist, album, track):
        '''lookup musicbrainz artist id with query of artist and album/track'''
        artistid = self.mb.get_artist_id(artist, album, track)
        if not artistid:
            artistid = self.audiodb.get_artist_id(artist, album, track)
        if not artistid:
            artistid = self.lastfm.get_artist_id(artist, album, track)
        return artistid

    def get_mb_album_id(self, artist, album, track):
        '''lookup musicbrainz album id with query of artist and album/track'''
        albumid = self.mb.get_album_id(artist, album, track)
        if not albumid:
            albumid = self.audiodb.get_album_id(artist, album, track)
        if not albumid:
            albumid = self.lastfm.get_album_id(artist, album, track)
        return albumid

    def get_artistpath_by_songpath(self, songpath, artist):
        '''get the artist path on disk by listing the song's path'''
        result = ""
        if "\\" in songpath:
            delim = "\\"
        else:
            delim = "/"
        # just move up the directory tree (max 3 levels) untill we find the directory
        for trypath in [songpath.rsplit(delim, 2)[0] + delim,
                        songpath.rsplit(delim, 3)[0] + delim, songpath.rsplit(delim, 1)[0] + delim]:
            if trypath.split(delim)[-2].lower() == artist.lower():
                result = trypath
                break
        return result

    @staticmethod
    def get_albumpath_by_songpath(songpath):
        '''get the album path on disk by listing the song's path'''
        result = ""
        if "\\" in songpath:
            delim = "\\"
        else:
            delim = "/"
        return songpath.rsplit(delim, 1)[0] + delim

    @staticmethod
    def lookup_artistart_in_folder(folderpath):
        '''lookup artwork in given folder'''
        artwork = {}
        files = xbmcvfs.listdir(folderpath)[1]
        for item in files:
            item = item.decode("utf-8")
            if item in ["banner.jpg", "clearart.png", "poster.png", "fanart.jpg", "landscape.jpg"]:
                key = item.split(".")[0]
                artwork[key] = folderpath + item
            elif item == "logo.png":
                artwork["clearlogo"] = folderpath + item
            elif item == "folder.jpg":
                artwork["thumb"] = folderpath + item
        # extrafanarts
        efa_path = folderpath + "extrafanart/"
        if xbmcvfs.exists(efa_path):
            files = xbmcvfs.listdir(efa_path)[1]
            artwork["fanarts"] = []
            if files:
                artwork["extrafanart"] = efa_path
                for item in files:
                    item = efa_path + item.decode("utf-8")
                    artwork["fanarts"].append(item)
        return artwork

    @staticmethod
    def lookup_albumart_in_folder(folderpath):
        '''lookup artwork in given folder'''
        artwork = {}
        files = xbmcvfs.listdir(folderpath)[1]
        for item in files:
            item = item.decode("utf-8")
            if item in ["cdart.png", "disc.png"]:
                artwork["discart"] = folderpath + item
            elif item == "folder.jpg":
                artwork["thumb"] = folderpath + item
        return artwork

    def get_custom_album_path(self, custom_path, artist, album, disc):
        '''try to locate the custom path for the album'''
        artist_path = self.get_customfolder_path(custom_path, artist)
        album_path = ""
        if artist_path:
            album_path = self.get_customfolder_path(artist_path, album)
            if album_path and disc:
                if "\\" in customfolder:
                    delim = "\\"
                else:
                    delim = "/"
                dirs = xbmcvfs.listdir(album_path)[0]
                for directory in dirs:
                    directory = directory.decode("utf-8")
                    if disc in directory:
                        return os.path.join(customfolder, directory) + delim
        return album_path

    def get_customfolder_path(self, customfolder, foldername):
        '''search recursively for a specific folder'''
        if "\\" in customfolder:
            delim = "\\"
        else:
            delim = "/"
        dirs = xbmcvfs.listdir(customfolder)[0]
        for strictness in [1, 0.95, 0.9, 0.8]:
            for directory in dirs:
                directory = directory.decode("utf-8")
                curpath = os.path.join(customfolder, directory) + delim
                match = SM(None, foldername.lower(), directory.lower()).ratio()
                if match >= strictness:
                    return curpath
                else:
                    return self.get_customfolder_path(curpath, foldername)
        return ""

    def download_artwork(self, folderpath, artwork):
        '''download artwork to local folder'''
        efa_path = ""
        new_dict = {}
        for key, value in artwork.iteritems():
            if key == "fanart":
                new_dict[key] = self.download_image(os.path.join(folderpath, "fanart.jpg"), value)
            elif key == "thumb":
                new_dict[key] = self.download_image(os.path.join(folderpath, "folder.jpg"), value)
            elif key == "discart":
                new_dict[key] = self.download_image(os.path.join(folderpath, "disc.png"), value)
            elif key == "banner":
                new_dict[key] = self.download_image(os.path.join(folderpath, "banner.jpg"), value)
            elif key == "clearlogo":
                new_dict[key] = self.download_image(os.path.join(folderpath, "logo.png"), value)
            elif key == "fanarts":
                efa_path = "%sextrafanart/" % folderpath
                if value and not xbmcvfs.exists(efa_path):
                    xbmcvfs.mkdir(efa_path)
                images = []
                for count, image in enumerate(value):
                    image = self.download_image(os.path.join(efa_path, "fanart%s.jpg" % count), image)
                    images.append(image)
                new_dict[key] = images
            else:
                new_dict[key] = value
        if efa_path:
            new_dict["extrafanart"] = efa_path
        return new_dict

    @staticmethod
    def download_image(filename, url):
        '''download specific image to local folder'''
        if xbmcvfs.exists(filename):
            # we do not overwrite existing images!
            return filename
        else:
            if xbmcvfs.copy(url, filename):
                return filename
        return url
