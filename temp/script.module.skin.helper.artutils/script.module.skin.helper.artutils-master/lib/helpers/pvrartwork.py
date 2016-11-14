 #!/usr/bin/python
# -*- coding: utf-8 -*-
from utils import get_clean_image, DialogSelect, log_msg, extend_dict, ADDON_ID
import xbmc
import xbmcgui
import xbmcvfs
from difflib import SequenceMatcher as SM
from operator import itemgetter
import re
from datetime import timedelta
from simplecache import use_cache
from urllib import quote_plus


class PvrArtwork(object):
    '''get artwork for kodi pvr'''

    def __init__(self, artutils=None):
        '''Initialize - optionaly provide our base ArtUtils class'''
        if not artutils:
            from artutils import ArtUtils
            self.artutils = ArtUtils
        else:
            self.artutils = artutils
        self.cache = self.artutils.cache

    def get_pvr_artwork(self, title, channel, genre="", manual_select=False, ignore_cache=False):
        '''
            collect full metadata and artwork for pvr entries
            parameters: title (required)
            channel: channel name (required)
            year: year or date (optional)
            genre: (optional)
            the more optional parameters are supplied, the better the search results
        '''
        # workaround for grouped recordings
        if not channel:
            channel, genre = self.get_pvr_channel_and_genre(title)

        # try cache first
        cache_str = "pvr_artwork.%s.%s" % (title.lower(), channel.lower())
        cache = self.artutils.cache.get(cache_str)
        if cache and not manual_select and not ignore_cache:
            log_msg("get_pvr_artwork - return data from cache - %s" % cache_str)
            return cache

        # no cache - start our lookup adventure
        log_msg("get_pvr_artwork - no data in cache - start lookup - %s" % cache_str)
        details = {}
        details["pvrtitle"] = title
        details["pvrchannel"] = channel
        details["pvrgenre"] = genre
        details["cachestr"] = cache_str
        details["media_type"] = ""

        # filter genre unknown/other
        if genre in xbmc.getLocalizedString(19499) or xbmc.getLocalizedString(19499) in genre.lower():
            details["genre"] = []
            genre = ""
            log_msg("genre is unknown so ignore....")
        else:
            details["genre"] = genre.split(" / ")
            details["media_type"] = self.get_mediatype_from_genre(genre)
        searchtitle = self.get_searchtitle(title, channel)

        # only continue if we pass our basic checks
        proceed_lookup = self.pvr_proceed_lookup(title, channel, genre)
        if not proceed_lookup and manual_select:
            # warn user about active skip filter
            proceed_lookup = xbmcgui.Dialog().yesno(
                line1=self.artutils.addon.getLocalizedString(32027),
                heading=xbmc.getLocalizedString(750))

        if proceed_lookup:

            # if manual lookup get the title from the user
            if manual_select:
                searchtitle = xbmcgui.Dialog().input(xbmc.getLocalizedString(16017), searchtitle,
                                                     type=xbmcgui.INPUT_ALPHANUM).decode("utf-8")
                if not searchtitle:
                    return

            # lookup recordings database
            details = extend_dict(details, self.lookup_local_recordings(title))
            # lookup custom path
            details = extend_dict(details, self.lookup_custom_path(searchtitle, title))
            # lookup movie/tv library
            details = extend_dict(details, self.lookup_local_library(searchtitle, details["media_type"]))

            # do internet scraping if results were not found in local db and scraping is enabled
            if self.artutils.addon.getSetting("pvr_art_scraper") == "true" and not details.get("art"):

                # prefer tvdb scraping
                tvdb_match = None
                if "movie" not in details["media_type"]:
                    tvdb_match = self.lookup_tvdb(searchtitle, channel, manual_select=manual_select)

                if tvdb_match:
                    # get full tvdb results and extend with tmdb
                    details["media_type"] = "tvshow"
                    details = extend_dict(details, self.artutils.thetvdb.get_series(tvdb_match))
                    details = extend_dict(details, self.artutils.tmdb.get_video_details_by_external_id(
                        tvdb_match, "tvdb_id"), ["poster", "fanart"])
                else:
                    # tmdb scraping for movies
                    tmdb_result = self.artutils.get_tmdb_details(
                        "", "", searchtitle, "", manual_select=manual_select, preftype=details["media_type"])
                    if tmdb_result:
                        details["media_type"] = tmdb_result["media_type"]
                        details = extend_dict(details, tmdb_result)

                if not details.get("art"):
                    details["art"] = {}

                # fanart.tv scraping - append result to existing art
                fanarttv_art = {}
                if details.get("imdbnumber") and details["media_type"] == "movie":
                    details["art"] = extend_dict(
                        details["art"], self.artutils.fanarttv.movie(
                            details["imdbnumber"]), [
                            "poster", "fanart", "landscape"])
                elif details.get("tvdb_id") and details["media_type"] == "tvshow":
                    details["art"] = extend_dict(
                        details["art"], self.artutils.fanarttv.tvshow(
                            details["tvdb_id"]), [
                            "poster", "fanart", "landscape"])

                # append omdb details
                if details.get("imdbnumber"):
                    details = extend_dict(
                        details, self.artutils.omdb.get_details_by_imdbid(
                            details["imdbnumber"]), [
                            "rating", "votes"])

                # set thumbnail - prefer scrapers
                thumb = ""
                if details.get("thumbnail"):
                    thumb = details["thumbnail"]
                elif details["art"].get("landscape"):
                    thumb = details["art"]["landscape"]
                elif details["art"].get("fanart"):
                    thumb = details["art"]["fanart"]
                elif details["art"].get("poster"):
                    thumb = details["art"]["poster"]
                # use google images as last-resort fallback for thumbs - if enabled
                elif self.artutils.addon.getSetting("pvr_art_google") == "true":
                    if manual_select:
                        google_title = searchtitle
                    else:
                        google_title = "%s + %s" % (searchtitle, channel.lower().split(" hd")[0])
                    thumb = self.artutils.google.search_image(google_title, manual_select)
                if thumb:
                    details["thumbnail"] = thumb
                    details["art"]["thumb"] = thumb
                # extrafanart
                if details["art"].get("fanarts"):
                    for count, item in enumerate(details["art"]["fanarts"]):
                        details["art"]["fanart.%s" % count] = item
                    if not details["art"].get("extrafanart") and len(details["art"]["fanarts"]) > 1:
                        details["art"]["extrafanart"] = "plugin://script.skin.helper.service/"\
                            "?action=extrafanart&fanarts=%s" % quote_plus(repr(details["art"]["fanarts"]))

        # store result in cache and return details
        self.artutils.cache.set(cache_str, details, expiration=timedelta(days=120))
        return details

    def manual_set_pvr_artwork(self, title, channel, genre):
        '''manual override artwork options'''

        artwork = self.get_pvr_artwork(title, channel, genre)
        cache_str = artwork["cachestr"]

        # show dialogselect with all artwork options
        abort = False
        while not abort:
            listitems = []
            for arttype in ["thumb", "poster", "fanart", "banner", "clearart", "clearlogo",
                            "discart", "landscape", "characterart"]:
                listitem = xbmcgui.ListItem(label=arttype, iconImage=artwork["art"].get(arttype, ""))
                listitem.setProperty("icon", artwork["art"].get(arttype, ""))
                listitems.append(listitem)
            w = DialogSelect("DialogSelect.xml", "", listing=listitems,
                             windowtitle=xbmc.getLocalizedString(13511), multiselect=False)
            w.doModal()
            selected_item = w.result
            del w
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
                    listitem = xbmcgui.ListItem(label=xbmc.getLocalizedString(13512), iconImage=image)
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

    def pvr_artwork_options(self, title, channel, genre):
        '''show options for pvr artwork'''
        if not channel and genre:
            channel, genre = self.get_pvr_channel_and_genre(title)
        ignorechannels = self.artutils.addon.getSetting("pvr_art_ignore_channels").split("|")
        ignoretitles = self.artutils.addon.getSetting("pvr_art_ignore_titles").split("|")
        options = []
        options.append(self.artutils.addon.getLocalizedString(32028))  # Refresh item (auto lookup)
        options.append(self.artutils.addon.getLocalizedString(32029))  # Refresh item (manual lookup)
        options.append(self.artutils.addon.getLocalizedString(32036))  # Choose art
        if channel in ignorechannels:
            options.append(self.artutils.addon.getLocalizedString(32030))  # Remove channel from ignore list
        else:
            options.append(self.artutils.addon.getLocalizedString(32031))  # Add channel to ignore list
        if title in ignoretitles:
            options.append(self.artutils.addon.getLocalizedString(32032))  # Remove title from ignore list
        else:
            options.append(self.artutils.addon.getLocalizedString(32033))  # Add title to ignore list
        options.append(self.artutils.addon.getLocalizedString(32034))  # Open addon settings
        header = self.artutils.addon.getLocalizedString(32035)
        dialog = xbmcgui.Dialog()
        ret = dialog.select(header, options)
        del dialog
        if ret == 0:
            # Refresh item (auto lookup)
            self.get_pvr_artwork(title=title, channel=channel, genre=genre, ignore_cache=True, manual_select=False)
        elif ret == 1:
            # Refresh item (manual lookup)
            self.get_pvr_artwork(title=title, channel=channel, genre=genre, ignore_cache=True, manual_select=True)
        elif ret == 2:
            # Choose art
            self.manual_set_pvr_artwork(title, channel, genre)
        elif ret == 3:
            # Add/remove channel to ignore list
            if channel in ignorechannels:
                ignorechannels.remove(channel)
            else:
                ignorechannels.append(channel)
            ignorechannels_str = "|".join(ignorechannels)
            self.artutils.addon.setSetting("pvr_art_ignore_channels", ignorechannels_str)
            self.get_pvr_artwork(title=title, channel=channel, genre=genre, ignore_cache=True, manual_select=False)
        elif ret == 4:
            # Add/remove title to ignore list
            if title in ignoretitles:
                ignoretitles.remove(title)
            else:
                ignoretitles.append(title)
            ignoretitles_str = "|".join(ignoretitles)
            self.artutils.addon.setSetting("pvr_art_ignore_titles", ignoretitles_str)
            self.get_pvr_artwork(title=title, channel=channel, genre=genre, ignore_cache=True, manual_select=False)
        elif ret == 5:
            # Open addon settings
            xbmc.executebuiltin("Addon.OpenSettings(%s)" % ADDON_ID)

    def get_pvr_channel_and_genre(self, title):
        '''workaround for grouped recordings, lookup recordinginfo in local db'''
        channel = ""
        genre = ""
        recordings = self.artutils.kodidb.recordings()
        for item in recordings:
            if item["title"].lower() in title.lower() or title.lower() in item["label"].lower():
                channel = item["channel"]
                genre = " / ".join(item["genre"])
                break
        return (channel, genre)

    def pvr_proceed_lookup(self, title, channel, genre):
        '''perform some checks if we can proceed with the lookup'''
        if not title or not channel:
            log_msg("PVR artwork - filter active for title: %s --> Title or channel is empty!")
            return False
        for item in self.artutils.addon.getSetting("pvr_art_ignore_titles").split("|"):
            if item.lower() == title.lower():
                log_msg(
                    "PVR artwork - filter active for title: %s channel: %s genre: %s --> "
                    "Title is in list of titles to ignore" %
                    (title, channel, genre))
                return False
        for item in self.artutils.addon.getSetting("pvr_art_ignore_channels").split("|"):
            if item.lower() == channel.lower():
                log_msg(
                    "PVR artwork - filter active for title: %s channel: %s genre: %s --> "
                    "Channel is in list of channels to ignore" %
                    (title, channel, genre))
                return False
        for item in self.artutils.addon.getSetting("pvr_art_ignore_genres").split("|"):
            if genre and item.lower() in genre.lower():
                log_msg(
                    "PVR artwork - filter active for title: %s channel: %s genre: %s --> "
                    "Genre is in list of Genres to ignore" %
                    (title, channel, genre))
                return False
        if self.artutils.addon.getSetting("pvr_art_ignore_commongenre") == "true":
            # skip common genres like sports, weather, news etc.
            genre = genre.lower()
            kodi_strings = [19516, 19517, 19518, 19520, 19548, 19549, 19551,
                            19552, 19553, 19554, 19555, 19556, 19557, 19558, 19559]
            for kodi_string in kodi_strings:
                kodi_string = xbmc.getLocalizedString(kodi_string).lower()
                if (genre and (genre in kodi_string or kodi_string in genre)) or kodi_string in title:
                    log_msg(
                        "PVR artwork - filter active for title: %s channel: %s genre: %s --> "
                        "Common genres like weather/sports are set to be ignored" %
                        (title, channel, genre))
                    return False
        if self.artutils.addon.getSetting("pvr_art_recordings_only") == "true":
            recordings = self.lookup_local_recordings(title)
            if not recordings:
                log_msg(
                    "PVR artwork - filter active for title: %s channel: %s genre: %s --> "
                    "PVR artwork is only enabled for recordings" %
                    (title, channel, genre))
                return False
        return True

    def get_mediatype_from_genre(self, genre):
        '''guess media type from genre for better matching'''
        media_type = ""
        if "movie" in genre.lower():
            media_type = "movie"
        elif "film" in genre.lower():
            media_type = "movie"
        # Kodi defined movie genres
        kodi_genres = [19500, 19507, 19508, 19602, 19603, ]
        for kodi_genre in kodi_genres:
            if genre == xbmc.getLocalizedString(kodi_genre):
                media_type = "movie"
        # Kodi defined tvshow genres
        kodi_genres = [19505, 19516, 19517, 19518, 19520, 19532, 19533, 19534, 19535, 19548, 19549,
                       19550, 19551, 19552, 19553, 19554, 19555, 19556, 19557, 19558, 19559]
        for kodi_genre in kodi_genres:
            if genre == xbmc.getLocalizedString(kodi_genre):
                media_type = "movie"
        return media_type

    def get_searchtitle(self, title, channel):
        '''common logic to get a proper searchtitle from crappy titles provided by pvr'''
        if not isinstance(title, unicode):
            title = title.decode("utf-8")
        title = title.lower()
        # split characters - split on common splitters
        splitters = self.artutils.addon.getSetting("pvr_art_splittitlechar").split("|")
        splitters.append(" %s" % channel.lower())
        for splitchar in splitters:
            title = title.split(splitchar)[0]
        # replace common chars and words
        re.sub(self.artutils.addon.getSetting("pvr_art_replace_by_space"), ' ', title)
        re.sub(self.artutils.addon.getSetting("pvr_art_stripchars"), '', title)
        return title

    @use_cache(2)
    def lookup_local_recordings(self, title):
        '''lookup actual recordings to get details for grouped recordings
           also grab a thumb provided by the pvr
        '''
        details = {}
        recordings = self.artutils.kodidb.recordings()
        for item in recordings:
            if title.lower() in item["title"].lower():
                if item.get("art"):
                    details["thumbnail"] = get_clean_image(item["art"].get("thumb"))
                # ignore tvheadend thumb as it returns the channellogo
                elif item.get("icon") and "imagecache" not in item["icon"]:
                    details["thumbnail"] = get_clean_image(item["icon"])
                details["channelname"] = item["channel"]
        if len(recordings) > 1:
            details["media_type"] = "tvshow"
        return details

    def lookup_tvdb(self, searchtitle, channel, manual_select=False):
        '''helper to select a match on tvdb'''
        tvdb_match = None
        searchtitle = searchtitle.lower()
        tvdb_result = self.artutils.thetvdb.search_series(searchtitle, True)
        searchchannel = channel.lower().split("hd")[0].replace(" ", "")
        match_results = []
        for item in tvdb_result:
            item["score"] = 0
            itemtitle = item["seriesName"].lower()
            network = item["network"].lower().replace(" ", "")
            # high score if channel name matches
            if network in searchchannel or searchchannel in network:
                item["score"] += 800
            # exact match on title - very high score
            if searchtitle == itemtitle:
                item["score"] += 1000
            # match title by replacing some characters
            if re.sub('\*|,|.\"|\'| |:|;', '', searchtitle) == re.sub('\*|,|.\"|\'| |:|;', '', itemtitle):
                item["score"] += 750
            # add SequenceMatcher score to the results
            stringmatchscore = SM(None, searchtitle, itemtitle).ratio()
            if stringmatchscore > 0.7:
                item["score"] += stringmatchscore * 500
            # prefer items with native language as we've searched with localized info enabled
            if item["overview"]:
                item["score"] += 250
            # prefer items with artwork
            if item["banner"]:
                item["score"] += 1
            if item["score"] > 500 or manual_select:
                match_results.append(item)
        # sort our new list by score
        match_results = sorted(match_results, key=itemgetter("score"), reverse=True)
        if match_results and manual_select:
            # show selectdialog to manually select the item
            listitems = []
            for item in match_results:
                thumb = "http://thetvdb.com/banners/%s" % item["banner"] if item["banner"] else ""
                listitem = xbmcgui.ListItem(label=item["seriesName"], iconImage=thumb)
                listitems.append(listitem)
            w = DialogSelect(
                "DialogSelect.xml",
                "",
                listing=listitems,
                window_title="%s - TVDB" %
                xbmc.getLocalizedString(283))
            w.doModal()
            selected_item = w.result
            del w
            if selected_item != -1:
                tvdb_match = match_results[selected_item]["id"]
            else:
                match_results = []
        if not tvdb_match and match_results:
            # just grab the first item as best match
            tvdb_match = match_results[0]["id"]
        return tvdb_match

    def lookup_custom_path(self, searchtitle, title):
        '''looks up a custom directory if it contains a subdir for our title'''
        details = {}
        details["art"] = {}
        custom_path = self.artutils.addon.getSetting("pvr_art_custom_path")
        if custom_path and self.artutils.addon.getSetting("pvr_art_custom") == "true":
            delim = "\\" if "\\" in custom_path else "/"
            dirs, files = xbmcvfs.listdir(custom_path)
            title_path = ""
            for strictness in [1, 0.95, 0.9, 0.8]:
                if title_path:
                    break
                for dir in dirs:
                    if title_path:
                        break
                    dir = dir.decode("utf-8")
                    curpath = os.path.join(custom_path, dir) + delim
                    for item in [title, searchtitle]:
                        match = SM(None, item, dir).ratio()
                        if match >= strictness:
                            title_path = curpath
                            break
            if title_path:
                # we have found a folder for the title, look for artwork
                files = xbmcvfs.listdir(title_path)[1]
                for item in files:
                    item = item.decode("utf-8")
                    if item in ["banner.jpg", "clearart.png", "poster.png", "fanart.jpg", "landscape.jpg"]:
                        key = item.split(".")[0]
                        details["art"][key] = title_path + item
                    elif item == "logo.png":
                        details["art"]["clearlogo"] = title_path + item
                    elif item == "thumb.jpg":
                        details["art"]["thumb"] = title_path + item
                # extrafanarts
                efa_path = title_path + "extrafanart" + delim
                if xbmcvfs.exists(title_path + "extrafanart"):
                    files = xbmcvfs.listdir(efa_path)[1]
                    details["art"]["fanarts"] = []
                    if files:
                        details["art"]["extrafanart"] = efa_path
                        for item in files:
                            item = efa_path + item.decode("utf-8")
                            details["art"]["fanarts"].append(item)
        return details

    def lookup_local_library(self, title, media_type):
        '''lookup the title in the local video db'''
        details = {}
        filters = [{"operator": "is", "field": "title", "value": title}]
        if not media_type or media_type == "tvshow":
            kodi_items = self.artutils.kodidb.tvshows(filters=filters, limits=(0, 1))
            if kodi_items:
                details = kodi_items[0]
                details["media_type"] = "tvshow"
        if not details and (not media_type or media_type == "movie"):
            kodi_items = self.artutils.kodidb.movies(filters=filters, limits=(0, 1))
            if kodi_items:
                details = kodi_items[0]
                details["media_type"] = "movie"
        if details:
            for artkey, artvalue in details["art"].iteritems():
                details["art"][artkey] = get_clean_image(artvalue)
            # todo: check extrafanart ?
        return details
