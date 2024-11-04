import html
import urllib.parse

from cleo.commands.command import Command

from streamseeker.api.handler import StreamseekerHandler
from streamseeker.api.streams.stream_base import StreamBase

from streamseeker.api.core.logger import Logger
logger = Logger().instance()


class AniworldtoDownloadCommand:
    def __init__(self, cli: Command, stream: StreamBase):
        self.cli = cli
        self.stream = stream

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata

        streamseek_handler = StreamseekerHandler()
        
        show = self.ask_show(streamseek_handler, self.stream)

        if show is None:
            return 0
        
        show_info = streamseek_handler.search(self.stream.get_name(), show.get('link'))

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
        
        download_mode = self.ask_download_mode()

        if download_mode is None:
            return 0
        
        if download_mode == "All after":
            download_mode = "all"
        elif download_mode == "Only one":
            download_mode = "single"

        season = 0
        episode = 0    
        if show_type in ["movie", "filme"]:
            label = "Choose a movie:"
            movies = list(map(lambda x: f"Movie {x}", show_info.get('movies')))
            season = self.ask_number(label, movies)

            if season is None:
                return 0
            
            season = int(season.replace("Movie ", ""))

            if len(seasons) == 1:
                self.cli.line(f"{show.get('name')} - movie {season}")
                self.cli.line("")
        
        if show_type in ["serie", "series", "staffel"]:
            label = "Choose a season:"
            seasons = list(map(lambda x: f"Season {x}", show_info.get('series')))
            season = self.ask_number(label, seasons)

            if season is None:
                return 0
            
            season = int(season.replace("Season ", ""))

            if len(seasons) == 1:
                self.cli.line(f"{show.get('name')} - season {season}")
                self.cli.line("")
            
            episodes = streamseek_handler.search_episodes(self.stream.get_name(), show.get('link'), show_type, season)
            label = "Choose an episode:"
            _episodes = list(map(lambda x: f"Episode {x}", episodes))
            episode = self.ask_number(label, _episodes)

            if episode is None:
                return 0

            episode = int(episode.replace("Episode ", ""))

            if len(_episodes) == 1:
                self.cli.line(f"{show.get('name')} - Episode {episode}")
                self.cli.line("")
        
        search_details = streamseek_handler.search_details(self.stream.get_name(), show.get('link'), show_type, season, episode)
         
        language = self.ask_language(search_details.get('languages'))

        if language is None:
            return 0
        
        preferred_provider = self.ask_provider(search_details.get('providers'))

        if preferred_provider is None:
            return 0
        try:
            streamseek_handler.download(download_mode, self.stream.get_name(), preferred_provider, show.get('link'), language, show_type, season, episode)     
        except KeyboardInterrupt:
            self.cli.line(
f"""\
----------------------------------------------------------
--------- Downloads may still be running. ----------------
----------------------------------------------------------

Please don't close this terminal window until it's done.
"""
)

        except Exception as e:self.cli.line(
f"""\
----------------------------------------------------------
Exception: {e}
----------------------------------------------------------

Please don't close this terminal window until it's done.
"""
)
        
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
        choice = self.cli.choice(
            "Choose a download mode:",
            ["All after", "Only one", "-- Quit --"],
            attempts=3,
            default=2,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice

    def ask_number(self, label:str, list: list[int]) -> int:
        if len(list) == 0:
            return None
        
        if len(list) == 1:
            return list[0]

        _list = list.copy()
        _list.insert(0, "-- Quit --")

        choice = self.cli.choice(
            label,
            _list,
            attempts=3,
            default=0,
        )
        self.cli.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice
