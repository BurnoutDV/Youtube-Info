# Pull All Youtube Videos from a Playlist, all Playlists from a channel
import atexit
import json
import sys
import curses
import re

import httplib2
from apiclient.discovery import build
from termcolor import colored
from datetime import datetime

try:
    stdscr = curses.initscr()
    curses.start_color()
    curses.cbreak()
except curses.error:
    stdscr = None

DEVELOPER_KEY = "LOAD FROM CONFIG"  # Youtube API Key, must be created via console
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
CHANNEL = ""  # Name of the Youtube Channel you want to use as a startpoint, might not be unique
CHANNEL_ID = ""


def exit_handler():
    if stdscr is not None:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

def load_config(fileName="config.json"):
    global DEVELOPER_KEY, CHANNEL, CHANNEL_ID
    try:
        with open(fileName) as json_file:
            data = json.load(json_file)
            # insert checks for keys existing here
            DEVELOPER_KEY = data['API_KEY']
            CHANNEL = data['Channel']
            CHANNEL_ID = data['ChannelID']
            json_file.close()
    except FileNotFoundError:
        sys.stderr.write("Config File not Found")
        sys.exit()


def load_from_file(file_name, cleanup=None):
    try:
        with open(file_name) as json_file:
            json_content = json.load(json_file)
            if cleanup == "playlist":
                return clean_playlist_data(json_content)
            if cleanup == "playlistlist":
                return clean_playlist_s_data(json_content)
            else:
                return json_content
    except FileNotFoundError:
        sys.stderr.write("File {} not found.".format(file_name))
    finally:
        json_file.close()


def fetch_all_playlists(channelID):
    res = YOUTUBE.playlists().list(channelId=channelID, part='contentDetails, snippet', maxResults='50').execute()
    next_page_token = res.get('nextPageToken')
    while 'nextPageToken' in res:
        print(colored(next_page_token, "cyan"))
        next_page = YOUTUBE.playlists().list(
                channelId=channelID,
                part='snippet',
                maxResults='50',
                pageToken=next_page_token).execute()
        res['items'] = res['items'] + next_page['items']

        if 'nextPageToken' not in next_page:
            res.pop('nextPageToken', None)
        else:
            next_page_token = next_page['nextPageToken']

    return res


def fetch_all_playlist_videos(playlistId):
    """
    Source: https://stackoverflow.com/a/31795605
    Fetches a playlist of videos from youtube
    We splice the results together in no particular order

    Parameters:
        parm1 - (string) playlistId
    Returns:
        playListItem Dict
    """
    res = YOUTUBE.playlistItems().list(
    part="snippet",
    playlistId=playlistId,
    maxResults="50"
    ).execute()

    next_page_token = res.get('nextPageToken')
    while ('nextPageToken' in res):
        next_page = YOUTUBE.playlistItems().list(
            part="snippet",
            playlistId=playlistId,
            maxResults="50",
            pageToken=next_page_token
            ).execute()
        res['items'] = res['items'] + next_page['items']

        if 'nextPageToken' not in next_page:
            res.pop('nextPageToken', None)
        else:
            next_page_token = next_page['nextPageToken']

    return res

def clean_playlist_s_data(raw_playlist_s_data):
    # processes and check the raw data of a list of playlists
    # checks
    if ('pageInfo' not in raw_playlist_s_data or
            'totalResults' not in raw_playlist_s_data['pageInfo']):
        return -1
    # process:
    clean_playlist_s = {
        'len': raw_playlist_s_data.get('pageInfo').get('totalResults'),
        'items': []
    }
    for entry in raw_playlist_s_data.get('items'):
        if('snippet' not in entry or
           'id' not in entry or
           'contentDetails' not in entry or
           'etag' not in entry):
            continue  # i am questioning wether i should just work with exceptions
        else:
            snippet = entry.get('snippet')
            if('title' not in snippet or
               'description' not in snippet or
               'publishedAt' not in snippet or
               'channelId' not in snippet):
                sys.stderr.write("snippet error")
                continue
            item = {"id": entry.get('id'),
                    "etag": entry.get('etag'),
                    "title": snippet.get('title'),
                    "description": snippet.get('description'),
                    "published": snippet.get('published'),
                    "channelID": snippet.get("channelId"),
                    "itemcount": entry.get("contentDetails").get("itemCount")
                    }
            clean_playlist_s['items'].append(item)

    return clean_playlist_s


def clean_playlist_data(raw_playlist_data):
    # processes and checks raw data of one playlist for inconsistencies
    # checks:
    if('pageInfo' not in raw_playlist_data or
    'totalResults' not in raw_playlist_data['pageInfo']):
        return -1
    # process:
    clean_playlist = {
        'len': raw_playlist_data.get('pageInfo').get('totalResults'),
        'items': []
    }
    for entry in raw_playlist_data.get('items'):
        if 'snippet' not in entry:
            continue
        else:
            snippet = entry.get('snippet')
            if ('position' not in snippet or
                    'title' not in snippet or
                    'description' not in snippet or
                    'publishedAt' not in snippet or
                    'channelId' not in snippet or
                    'resourceId' not in snippet or
                    'videoId' not in snippet['resourceId']):
                continue
            item = {
                'position': snippet.get('position'),
                'title': snippet.get('title'),
                'description': snippet.get("description"),
                'published': snippet.get('publishedAt'),
                'channelID': snippet.get('channelId'),
                'videoID': snippet.get('resourceId').get('videoId')
            }
            clean_playlist['items'].append(item)

    return clean_playlist


def playlist_as_cli_list(clean_playlist_data, max_results=0, ltrim=0):
    i = 1
    playlist_items = clean_playlist_data.get('items').copy()
    # copy so we can adjust length with ncurse without messing with the base data
    if stdscr is not None:
        height, width = stdscr.getmaxyx()
        # print("This screen is {}x{}".format(height, width), end="\n\r")
        # iterate two times to check max length for position and entry len, then trim title
        pos_len = 0
        des_len = 0
        for entry in playlist_items:
            cur_len = len(str(entry['position']))
            if cur_len > pos_len:
                pos_len = cur_len
            cur_len = len(str(len(entry['description'])))
            if cur_len > des_len:
                des_len = cur_len
        title_len = width - 2 - des_len - 1 - pos_len - 1  # 2 chars for whitespace between columns
        # print("Screen width: {} -> {} + {} + {} +4".format(width, pos_len, title_len, des_len), end="\n\r")
        for entry in playlist_items:
            entry['position'] = str(entry['position']).ljust(pos_len)
            entry['title'] = entry['title'][ltrim:]
            entry['title'] = entry['title'][:title_len-2] + (entry['title'][title_len-2:] and '..')
            entry['title'] = str(entry['title']).ljust(title_len)
            entry['desc_len'] = str(len(entry['description'])).ljust(des_len)
    for entry in playlist_items:
        i += 1
        sys.stdout.write(
              " "
              + colored(entry['position'], "green", None)
              + " "
              + colored(entry['title'], "white")
              + " "
              + colored(entry.get('desc_len', len(entry.get('description'))), "cyan")
              + " "
        )
        if 0 < max_results < i:
            break
    sys.stdout.write(colored("Das ist ein Text", "red"))


# TODO curses bullshit here, need clean up data first


def all_playlists_as_cli_list(raw_playlists_data, max_results=0):
    i = 1
    for entry in raw_playlists_data.get('items'):
        i += 1
        playlist = entry.get('snippet')
        item_count = entry.get('contentDetails').get('itemCount')
        title = playlist.get('title')
        description = playlist.get('description')
        print(colored(title, "white"),
              "\t",
              colored(item_count, "green"),
              "\t",
              colored(len(description), "cyan")
            )

        if 0 < max_results < i:
            break


# === UTILITY Programs, should probably externalise

def generate_markdown_from_playlist(raw_playlists_data, fileName="", title="Playlist Data"):
    #  either saves playlist information directly to file or pipes them to std.out
    now = datetime.now()
    outtext = "# {}\n\n".format(title)
    outtext += "*{} Einträge in dieser Liste, abgerufen am **{}***\n\n".format(
        raw_playlists_data.get('pageInfo').get('totalResults'),
        now.strftime("%d.%m.%Y %H:%M Uhr")
    )
    for entry in raw_playlists_data.get('items'):
        video = entry.get('snippet')
        position = video.get('position')
        title = video.get('title')
        description = video.get("description")
        published = video.get('publishedAt')
        published = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
        outtext += "##### #{}\n".format(str(position+1))
        outtext += "* Titel: `{}`\n\n".format(title)
        outtext += "* Beschreibung:\n\n"
        outtext += "```markdown\n"
        outtext += description
        outtext += "\n```\n\n"
        outtext += "*Hochgeladen am: {}*\n\n".format(published.strftime("%d.%m.%Y %H:%M Uhr"))
    if fileName == "":
        print(outtext)
    else:
        try:
            write_file = open(fileName, "x")
            write_file.write(outtext)
        except FileExistsError:
            sys.stderr.write("File already exists.\n")
            return -1


def find_playlist_disorder(clean_playlist_data, regex_title_number=r"(\#[0-9]+\b)"):
    cor_num = 0
    for item in clean_playlist_data['items']:
        # print(re.search(regex_title_number, item.get('title')))
        #print(re.search(r"\d+",item.get('title')))
        try:
            number_str = re.search(regex_title_number, item.get('title'))
            pos_num = int(str(number_str.group())[1:])
            if pos_num != item.get('position')+1+cor_num:
                # error types
                # one missing vid
                # print(colored("pos{} = #{}".format(pos_num+cor_num+1,item.get('position')+1), "green"))
                if pos_num == item.get('position')+cor_num+2: # one element missing
                    print(colored("Missing Element after #{}".
                                  format(item.get('position')), "yellow"))
                    cor_num += 1
    # TODO: vertauschte Videos
                else:
                    print(colored("Missmatch found: {} - Pos:{} != #{}".
                                  format(item['title'], item['position']+1, pos_num+cor_num), "red"))
        except TypeError:
            print(colored("TypeError in 'item.title': {}. Maybe not right Dictionary Typ?".format(item.get('title'), "red")))
        except AttributeError:
            pass
            # print(colored("AttributeError -> no match for '{}' in '{}'".format(regex_title_number, item.get('title'), 'item.title'), "red"))


def cache_dump(filename, data, basepath="./cache/", ext="json", prefix=""):
    # saves the complete data structure locally, this is more or less just boilerplate to keep main code slim
    try:
        cache = open("{}{}{}.{}".format(basepath, prefix, filename, ext), "w")
        json.dump(data, cache, indent=3)
        cache.close()
    except: # super broad errorhandling
        print("Couldnt open file {}".format(filename), file=sys.stderr)


def fallback_load():
    # to conserve api tickets for repeating queries we cache all the data in plain json files on disk instead of
    # requesting everything anew constantly.
    print("Nothing here")


def main():
    print("Nothing here")
    # videos = load_from_file("./one_playlist.json", cleanup="playlist")
    # playlists = load_from_file("./playlists.json")
    # playlist_as_cli_list(videos, ltrim=18)
    # find_playlist_disorder(videos)
    # all_playlists_as_cli_list(playlists, 20)
    # generate_markdown_from_playlist(videos, "dishonored.md")


def fetch_whole_channel_playlists(channel_id):
    # fetches all the playlist of a channel and then all corresponding playlists
    all_playlist_raw = fetch_all_playlists(channel_id)
    cache_dump(channel_id, all_playlist_raw, prefix="raw_")

    playlists = clean_playlist_s_data(all_playlist_raw)
    cache_dump(channel_id, playlists, prefix="clean_")
    for item in all_playlist_raw['items']:
        playlist_id = item.get('id')
        print(colored(item['snippet']['title'], "grey"))

        all_videos_raw = fetch_all_playlist_videos(playlist_id)
        cache_dump(playlist_id, all_videos_raw, prefix="raw_")

        videos = clean_playlist_data(all_videos_raw)
        cache_dump(playlist_id, videos, prefix="clean_")


if __name__ == '__main__':
    # exit stuff for curses, i actually don't know whether this is enough or not
    atexit.register(exit_handler)
    # init Youtube Object
    load_config()
    try:
        YOUTUBE = build(YOUTUBE_API_SERVICE_NAME,
                        YOUTUBE_API_VERSION,
                        developerKey=DEVELOPER_KEY)
    except httplib2.ServerNotFoundError:
        sys.stderr.write("Server not reachable, non-Internet functions will still work\n")
    # TODO: Create proper argparser interface here

    fetch_whole_channel_playlists(CHANNEL_ID)