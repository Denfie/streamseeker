import html
import os
import urllib.parse

from cleo.commands.command import Command

from streamseeker.api.handler import StreamseekerHandler
from streamseeker.api.core.downloader.helper import DownloadHelper
from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.streams.stream_base import StreamBase

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class StoDownloadCommand:
    def __init__(self, cli: Command, stream: StreamBase):
        self.cli = cli
        self.stream = stream

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata

        streamseek_handler = StreamseekerHandler()
        
        show = self.ask_show(streamseek_handler, self.stream)

        if show is None:
            return 0
        
        try:
            show_info = streamseek_handler.search(self.stream.get_name(), show.get('link'))
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.cli.line("<error>Could not connect to the server. Please try again later.</error>")
            return 0

        if show_info is None:
            self.cli.line("Can't get further information about show.")
            return 0
        
        show_type = None
        if len(show_info.get('types')) == 1:
            show_type = show_info.get('types')[0]
        if len(show_info.get('types')) > 1:
            show_type = self.ask_show_type(show_info.get('types'))
            
            if show_type is None:
                return 0
        
        season = 0
        episode = 0
        episodes = None
        download_mode = "single"

        if show_type in ["movie", "filme"]:
            label = "Choose a movie:"
            movies = list(map(lambda x: f"Movie {x}", show_info.get('movies')))
            season = self.ask_number(label, movies, show_name=show.get('link'), type_=show_type)

            if season is None:
                return 0

            season = int(season.replace("Movie ", ""))

            if len(movies) == 1:
                self.cli.line(f"{show.get('name')} - movie {season}")
                self.cli.line("")

        elif show_type in ["serie", "series", "staffel"]:
            download_mode = self.ask_download_mode()

            if download_mode is None:
                return 0

            label = "Choose a season:"
            seasons = list(map(lambda x: f"Season {x}", show_info.get('series')))
            season = self.ask_number(label, seasons, show_name=show.get('link'), type_=show_type)

            if season is None:
                return 0

            season = int(season.replace("Season ", ""))

            if len(seasons) == 1:
                self.cli.line(f"{show.get('name')} - season {season}")
                self.cli.line("")

            if download_mode != "season":
                try:
                    episodes = streamseek_handler.search_episodes(self.stream.get_name(), show.get('link'), show_type, season)
                except Exception as e:
                    logger.error(f"Connection error: {e}")
                    self.cli.line("<error>Could not fetch episodes. Please try again later.</error>")
                    return 0
                label = "Choose an episode:"
                _episodes = list(map(lambda x: f"Episode {x}", episodes))
                episode = self.ask_number(label, _episodes, show_name=show.get('link'), type_=show_type, season=season)

                if episode is None:
                    return 0

                episode = int(episode.replace("Episode ", ""))

                if len(_episodes) == 1:
                    self.cli.line(f"{show.get('name')} - Episode {episode}")
                    self.cli.line("")
            else:
                episode = 0

        detail_episode = episode if episode > 0 else 1
        try:
            search_details = streamseek_handler.search_details(self.stream.get_name(), show.get('link'), show_type, season, detail_episode)
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.cli.line("<error>Could not fetch details. Please try again later.</error>")
            return 0

        language = self.ask_language(search_details.get('languages'))

        if language is None:
            return 0

        preferred_provider = self.ask_provider(search_details.get('providers'))

        if preferred_provider is None:
            return 0

        from streamseeker.api.core.downloader.processor import QueueProcessor

        from streamseeker.i18n import t

        def _added_msg(count: int) -> str:
            key = "queue.added.singular" if count == 1 else "queue.added.plural"
            return f"<info>{t(key, count=count)}</info>"

        if download_mode == "single":
            streamseek_handler.enqueue_single(
                self.stream.get_name(), preferred_provider, show.get('link'),
                language, show_type, season, episode
            )
            self.cli.line(_added_msg(1))
        elif download_mode == "season":
            count = streamseek_handler.enqueue_all(
                self.stream.get_name(), preferred_provider, show.get('link'),
                language, show_type, season, 0,
                seasons_list=[season],
            )
            self.cli.line(_added_msg(count))
        elif download_mode == "season_from":
            count = streamseek_handler.enqueue_all(
                self.stream.get_name(), preferred_provider, show.get('link'),
                language, show_type, season, episode,
                seasons_list=[season],
                episodes_list=episodes,
            )
            self.cli.line(_added_msg(count))
        elif download_mode == "all":
            count = streamseek_handler.enqueue_all(
                self.stream.get_name(), preferred_provider, show.get('link'),
                language, show_type, season, episode,
                seasons_list=show_info.get('series') or show_info.get('movies'),
                episodes_list=episodes,
            )
            self.cli.line(_added_msg(count))

        QueueProcessor().start(config=streamseek_handler.config)

        return 0

    # Ask for streaming provider
    def ask_stream(self, seek_handler: StreamseekerHandler) -> StreamBase:
        streams = seek_handler.streams()

        if len(streams) == 0:
            return None
        
        if len(streams) == 1:
            return streams[0]

        _list: list[str] = []
        for stream in streams:
            _list.append(stream.get_title())
        _list.append("-- Quit --")

        choice = self.cli.choice(
            "Choose a streaming site:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        # Find stream from choice
        stream = None
        for _stream in streams:
            if _stream.get_title() == choice:
                stream = _stream
                break

        if stream is None:
            self.cli.line("Invalid stream choice")
            return None
        
        return stream

    # Ask and search for show
    def ask_show(self, seek_handler: StreamseekerHandler, show: StreamBase) -> dict:
        search_term = self.cli.ask("Enter show name:")
        self.cli.line("")

        search_term = urllib.parse.quote_plus(search_term)

        results = seek_handler.search_query(show.get_name(), search_term)
        _list: list[str] = []
        for _show in results:
            _show['name'] = html.unescape(_show.get('name'))
            _list.append(_show.get('name'))
        _list.append("-- Retry search --")
        _list.append("-- Quit --")

        choice = self.cli.choice(
            "Choose a show:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.cli.line("")

        if choice == "-- Quit --":
            return None
        
        if choice == "-- Retry search --":
            return self.ask_show(seek_handler, show)

        # Find stream from choice
        show = None
        for _show in results:
            if _show.get('name') == choice:
                show = _show
                break

        if show is None:
            self.cli.line("Invalid show choice")
            return None

        return show
    
    def ask_show_type(self, list: list[str]) -> str:
        if len(list) == 0:
            return None
        
        if len(list) == 1:
            return list[0]
        
        choice = self.cli.choice(
            "Choose a show type:",
            list,
            attempts=3,
            default=len(list) - 1,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice

    def ask_language(self, languages: dict) -> str:
        keys = list(languages.keys())

        if len(keys) == 0:
            return None
        
        if len(keys) == 1:
            return keys[0]

        _list: list[str] = []
        for language in languages.values():
            _list.append(language.get('title'))
        _list.append("-- Quit --")
        
        choice = self.cli.choice(
            "Choose a language:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        for language_key in languages.keys():
            language = languages.get(language_key)
            if language.get('title') == choice:
                return language_key
        
        return None

    def ask_provider(self, providers: dict) -> str:
        keys = list(providers.keys())
        if len(keys) == 0:
            return None
        
        if len(keys) == 1:
            return keys[0]
        
        _list: list[str] = []
        for provider in providers.values():
            _list.append(provider.get('title'))
        _list.append("-- Quit --")
        
        choice = self.cli.choice(
            "Choose a download provider:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        for provider_key in providers.keys():
            provider = providers.get(provider_key)
            if provider.get('title') == choice:
                return provider_key
        
        return None
    
    def ask_download_mode(self) -> str:
        modes = [
            "Full season",
            "Season from episode",
            "All from season onwards",
            "Only one episode",
            "-- Quit --",
        ]

        choice = self.cli.choice(
            "Choose a download mode:",
            modes,
            attempts=3,
            default=len(modes) - 1,
        )
        self.cli.line("")

        if choice == "-- Quit --":
            return None

        mode_map = {
            "Full season": "season",
            "Season from episode": "season_from",
            "All from season onwards": "all",
            "Only one episode": "single",
        }
        return mode_map.get(choice)

    def _get_episode_status(self, show_name: str, type_: str, season: int, episode: int) -> str:
        queue = DownloadManager.get_queue()
        for item in queue:
            if (item.get("name") == show_name
                and item.get("season") == season
                and item.get("episode") == episode):
                return item.get("status", "pending")
        helper = DownloadHelper()
        pattern = f"{show_name}-s{season}e{episode}-"
        if type_ == "filme":
            pattern = f"{show_name}-movie-{season}-"
        for line in helper.success_lines:
            if pattern in line:
                return "completed"
        return None

    def _get_season_status(self, show_name: str, type_: str, season: int) -> str:
        helper = DownloadHelper()
        queue = DownloadManager.get_queue()
        pattern = f"{show_name}-s{season}e" if type_ != "filme" else f"{show_name}-movie-{season}-"
        has_success = any(pattern in line for line in helper.success_lines)
        has_queue = any(
            item.get("name") == show_name and item.get("season") == season
            for item in queue
        )
        if has_success and not has_queue:
            return "completed"
        elif has_success or has_queue:
            return "partial"
        return None

    def _colorize_item(self, label: str, status: str | None) -> str:
        match status:
            case "completed":
                return f"\u2705 {label}"
            case "downloading" | "pending":
                return f"\u23f3 {label}"
            case "failed":
                return f"\u274c {label}"
            case "skipped":
                return f"\u23ed {label}"
            case "paused":
                return f"\u23f8 {label}"
            case "partial":
                return f"\u25d0 {label}"
            case _:
                return label

    def ask_number(self, label: str, list: list[int], show_name: str = None, type_: str = None, season: int = None) -> int:
        if len(list) == 0:
            return None

        if len(list) == 1:
            return list[0]

        _list = []
        for item in list:
            if show_name:
                if item.startswith("Episode "):
                    ep = int(item.replace("Episode ", ""))
                    status = self._get_episode_status(show_name, type_, season, ep)
                elif item.startswith("Season "):
                    s = int(item.replace("Season ", ""))
                    status = self._get_season_status(show_name, type_, s)
                elif item.startswith("Movie "):
                    m = int(item.replace("Movie ", ""))
                    status = self._get_episode_status(show_name, type_, m, 0)
                else:
                    status = None
                _list.append(self._colorize_item(item, status))
            else:
                _list.append(item)

        _list.insert(0, "-- Quit --")

        choice = self.cli.choice(
            label,
            _list,
            attempts=3,
            default=0,
        )
        self.cli.line("")

        if choice == "-- Quit --":
            return None

        import re as _re
        clean = _re.sub(r'^[\u2705\u23f3\u274c\u23ed\u23f8\u25d0]\s*', '', choice)
        return clean
