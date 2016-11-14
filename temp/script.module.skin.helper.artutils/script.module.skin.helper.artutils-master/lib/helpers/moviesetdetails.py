#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
    Returns complete (nicely formatted) information about the movieset and it's movies
'''

from kodi_constants import FIELDS_MOVIES
from utils import get_duration, get_clean_image
from urllib import quote_plus
import xbmc


def get_moviesetdetails(simplecache, kodidb, set_id, studiologos, studiologos_path):
    '''Returns complete (nicely formatted) information about the movieset and it's movies'''
    details = {}
    # try to get from cache first
    # use checksum compare based on playcounts because moviesets do not get refreshed automatically
    movieset = kodidb.movieset(set_id, ["playcount"])
    cache_str = "MovieSetDetails.%s" % (set_id)
    cache_checksum = []
    if movieset:
        cache_checksum = "%s.%s.%s" % (set_id, [movie["playcount"] for movie in movieset["movies"]], studiologos_path)
        cache = simplecache.get(cache_str, checksum=cache_checksum)
        if cache:
            return cache
        # process movieset listing - get full movieset including all movie fields
        movieset = kodidb.movieset(set_id, FIELDS_MOVIES)
        count = 0
        runtime = 0
        unwatchedcount = 0
        watchedcount = 0
        runtime = 0
        writer = []
        director = []
        genre = []
        country = []
        studio = []
        years = []
        plot = ""
        title_list = ""
        total_movies = len(movieset['movies'])
        title_header = "[B]%s %s[/B][CR]" % (total_movies, xbmc.getLocalizedString(20342))
        all_fanarts = []
        details["art"] = movieset["art"]
        for count, item in enumerate(movieset['movies']):
            if item["playcount"] == 0:
                unwatchedcount += 1
            else:
                watchedcount += 1

            # generic labels
            for label in ["label", "plot", "year", "rating"]:
                details['%s.%s' % (count, label)] = item[label]
            details["%s.DBID" % count] = item["movieid"]
            details["%s.Duration" % count] = item['runtime'] / 60

            # art labels
            art = item['art']
            for label in ["poster", "fanart", "landscape", "clearlogo", "clearart", "banner", "discart"]:
                if art.get(label):
                    details['%s.Art.%s' % (count, label)] = get_clean_image(art[label])
                    if not movieset["art"].get(label):
                        movieset["art"][label] = get_clean_image(art[label])
            all_fanarts.append(get_clean_image(art.get("fanart")))

            # streamdetails
            if item.get('streamdetails', ''):
                streamdetails = item["streamdetails"]
                audiostreams = streamdetails.get('audio', [])
                videostreams = streamdetails.get('video', [])
                subtitles = streamdetails.get('subtitle', [])
                if len(videostreams) > 0:
                    stream = videostreams[0]
                    height = stream.get("height", "")
                    width = stream.get("width", "")
                    if height and width:
                        resolution = ""
                        if width <= 720 and height <= 480:
                            resolution = "480"
                        elif width <= 768 and height <= 576:
                            resolution = "576"
                        elif width <= 960 and height <= 544:
                            resolution = "540"
                        elif width <= 1280 and height <= 720:
                            resolution = "720"
                        elif width <= 1920 and height <= 1080:
                            resolution = "1080"
                        elif width * height >= 6000000:
                            resolution = "4K"
                        details["%s.Resolution" % count] = resolution
                    details["%s.Codec" % count] = stream.get("codec", "")
                    if stream.get("aspect", ""):
                        details["%s.AspectRatio" % count] = round(stream["aspect"], 2)
                if len(audiostreams) > 0:
                    # grab details of first audio stream
                    stream = audiostreams[0]
                    details["%s.AudioCodec" % count] = stream.get('codec', '')
                    details["%s.AudioChannels" % count] = stream.get('channels', '')
                    details["%s.AudioLanguage" % count] = stream.get('language', '')
                if len(subtitles) > 0:
                    # grab details of first subtitle
                    details["%s.SubTitle" % count] = subtitles[0].get('language', '')

            title_list += "%s (%s)[CR]" % (item['label'], item['year'])
            if item['plotoutline']:
                plot += "[B]%s (%s)[/B][CR]%s[CR][CR]" % (item['label'], item['year'], item['plotoutline'])
            else:
                plot += "[B]%s (%s)[/B][CR]%s[CR][CR]" % (item['label'], item['year'], item['plot'])
            runtime += item['runtime']
            if item.get("writer"):
                writer += [w for w in item["writer"] if w and w not in writer]
            if item.get("director"):
                director += [d for d in item["director"] if d and d not in director]
            if item.get("genre"):
                genre += [g for g in item["genre"] if g and g not in genre]
            if item.get("country"):
                country += [c for c in item["country"] if c and c not in country]
            if item.get("studio"):
                studio += [s for s in item["studio"] if s and s not in studio]
            years.append(str(item['year']))
        details["Plot"] = plot
        if total_movies > 1:
            details["ExtendedPlot"] = title_header + title_list + "[CR]" + plot
        else:
            details["ExtendedPlot"] = plot
        details["Title"] = title_list
        details["Runtime"] = runtime / 60
        details.update(get_duration(runtime / 60))
        details["Writer"] = writer
        details["Director"] = director
        details["Genre"] = genre
        details["Studio"] = studio
        details["Years"] = years
        details["WatchedCount"] = watchedcount
        details["UnwatchedCount"] = unwatchedcount
        details["art"]["fanarts"] = all_fanarts
        details.update(studiologos.get_studio_logo(studio, studiologos_path))
        details["Count"] = total_movies
        details["art"]["ExtraFanart"] = "plugin://script.skin.helper.service/?action=extrafanart&fanarts=%s"\
            % quote_plus(repr(all_fanarts))
    simplecache.set(cache_str, details, checksum=cache_checksum)
    return details
