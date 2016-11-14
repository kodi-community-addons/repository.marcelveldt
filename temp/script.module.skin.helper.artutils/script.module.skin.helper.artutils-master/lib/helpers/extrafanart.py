#!/usr/bin/python
# -*- coding: utf-8 -*-
import os, xbmcvfs

def get_extrafanart(file_path, media_type):
    result = {}
    efa_path = ""
    folder_path = ""
    if "plugin.video.emby" in file_path:
        #workaround for emby addon
        efa_path = u"plugin://plugin.video.emby/extrafanart?path=" + file_path
    elif "plugin://" in file_path:
        folder_path = ""
    else:
        if file_path and "tvshow" in media_type:
            folder_path = file_path
        elif file_path and "movie" in media_type:
            folder_path = file_path
        elif file_path and "musicvideo" in media_type:
            folder_path = file_path
        elif file_path and "season" in media_type:
            folder_path = os.path.dirname(file_path)
        elif file_path and "episode" in media_type:
            folder_path = os.path.dirname(file_path)
                
        #lookup extrafanart folder
        if folder_path:
            if "/" in folder_path: 
                sep = u"/"
            else: 
                sep = u"\\"
            if not folder_path.endswith(sep):
                folder_path += sep
            efa_path = "%s%s%s" %(folder_path,"extrafanart",sep)
            if not xbmcvfs.exists(efa_path):
                efa_path = ""
        
    if efa_path:
        result["art"] = {
            "extrafanart": efa_path, 
            "fanarts": [] }
        for count, file in enumerate(xbmcvfs.listdir(efa_path)[1]):
            if file.lower().endswith(".jpg"):
                result["art"]["ExtraFanArt.%s"%count] = efa_path + file.decode("utf-8")
                result["art"]["fanarts"].append(efa_path + file.decode("utf-8"))
    return result