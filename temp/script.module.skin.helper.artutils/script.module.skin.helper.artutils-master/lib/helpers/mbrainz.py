#!/usr/bin/python
# -*- coding: utf-8 -*-
from utils import ADDON_ID, urlencode, get_compare_string, log_msg
from simplecache import use_cache
import xbmcvfs
import xbmcaddon


class MusicBrainz(object):
    '''get metadata from musicbrainz'''
    ignore_cache = False

    def __init__(self, simplecache=None):
        '''Initialize - optionaly provide simplecache object'''
        if not simplecache:
            from simplecache import SimpleCache
            self.cache = SimpleCache()
        else:
            self.cache = simplecache
        import musicbrainzngs as mb
        mb.set_useragent(
            "script.skin.helper.service",
            "1.0.0",
            "https://github.com/marcelveldt/script.skin.helper.service")
        mb.set_rate_limit(limit_or_interval=2.0, new_requests=1)
        addon = xbmcaddon.Addon(ADDON_ID)
        if addon.getSetting("music_art_mb_mirror"):
            mb.set_hostname(addon.getSetting("music_art_mb_mirror"))
        del addon
        self.mb = mb

    @use_cache(30)
    def search(self, artist, album, track):
        '''get musicbrainz id by query of artist, album and/or track'''
        mb_albums = []
        albumid = ""
        artistid = ""
        if artist and album:
            mb_albums = self.mb.search_release_groups(query=album,
                                                      limit=3, offset=None, strict=False, artist=artist)
        elif not mb_albums and artist and track:
            mb_albums = self.mb.search_recordings(query=track,
                                                  limit=3, offset=None, strict=False, artist=artist)
        elif not mb_albums and artist and album:
            # use albumname as track
            track = album
            mb_albums = self.mb.search_recordings(query=track,
                                                  limit=3, offset=None, strict=False, artist=artist)

        if mb_albums and mb_albums.get("release-group-list"):
            mb_albums = mb_albums.get("release-group-list")
        elif mb_albums and mb_albums.get("recording-list"):
            mb_albums = mb_albums.get("recording-list")

        for mb_album in mb_albums:
            if artistid:
                break
            if mb_album and isinstance(mb_album, dict):
                albumid = mb_album.get("id", "")
                if mb_album.get("artist-credit"):
                    for mb_artist in mb_album.get("artist-credit"):
                        if isinstance(mb_artist, dict) and mb_artist.get("artist", ""):
                            # safety check - only allow exact artist match
                            foundartist = mb_artist["artist"].get("name")
                            foundartist = foundartist.encode("utf-8").decode("utf-8")
                            if foundartist and get_compare_string(foundartist) == get_compare_string(artist):
                                artistid = mb_artist.get("artist").get("id")
                                break
                            if not artistid and mb_artist["artist"].get("alias-list"):
                                alias_list = [get_compare_string(item["alias"])
                                              for item in mb_artist["artist"]["alias-list"]]
                                if get_compare_string(artist) in alias_list:
                                    artistid = mb_artist.get("artist").get("id")
                                    break
            else:
                log_msg("mb_album not a dict! -- %s" % mb_album)
        if not artistid:
            albumid = ""
        return (artistid, albumid)

    def get_artist_id(self, artist, album, track):
        '''get musicbrainz id by query of artist, album and/or track'''
        return self.search(artist, album, track)[0]

    def get_album_id(self, artist, album, track):
        '''get musicbrainz id by query of artist, album and/or track'''
        return self.search(artist, album, track)[1]

    def get_albumthumb(self, albumid):
        '''get album thumb'''
        thumb = ""
        url = "http://coverartarchive.org/release-group/%s/front" % albumid
        if xbmcvfs.exists(url):
            thumb = url
        return thumb
