from __future__ import annotations

import urllib.parse

from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

from cleo.helpers import argument
from cleo.helpers import option

from streamseeker.api.handler import StreamseekerHandler
from streamseeker.api.streams.stream_base import StreamBase
from cleo.commands.command import Command

if TYPE_CHECKING:
    from collections.abc import Collection

    from cleo.io.inputs.argument import Argument
    from cleo.io.inputs.option import Option

class DownloadCommand(Command):
    name = "download"

    description = "Start interactive mode to download a show."

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata

        streamseek_handler = StreamseekerHandler()

        stream = self.ask_stream(streamseek_handler)

        if stream is None:
            return 0
        
        show = self.ask_show(streamseek_handler, stream)

        if show is None:
            return 0
        
        show_info = streamseek_handler.search(stream.get_name(), show.get('link'))

        if show_info is None:
            self.line("Can't get further information about show.")
            return 0
        
        show_type = None
        if len(show_info.get('types')) > 1:
            show_type = self.ask_show_type(show_info.get('types'))
            
            if show_type is None:
                return 0

        season = 0
        episode = 0    

        if show_type in ["movie", "filme"]:
            label = "Choose a movie:"
            movies = list(map(lambda x: f"Movie {x}", show_info.get('movies')))
            season = self.ask_number(label, movies)

            if season is None:
                return 0
            
            season = int(season.replace("Movie ", ""))
        
        language = self.ask_language(show_info.get('languages'))

        if language is None:
            return 0
        
        download_mode = self.ask_download_mode()

        if download_mode is None:
            return 0
        
        if download_mode == "All after":
            download_mode = "all"
        elif download_mode == "Only one":
            download_mode = "single"
        
        if show_type in ["serie", "series", "staffel"]:
            label = "Choose a season:"
            seasons = list(map(lambda x: f"Season {x}", show_info.get('series')))
            season = self.ask_number(label, seasons)

            if season is None:
                return 0
            
            season = int(season.replace("Season ", ""))
            
            episodes = streamseek_handler.search_episodes(stream.get_name(), show.get('link'), show_type, season)
            label = "Choose an episode:"
            _episodes = list(map(lambda x: f"Episode {x}", episodes))
            episode = self.ask_number(label, _episodes)

            if episode is None:
                return 0

            episode = int(episode.replace("Episode ", ""))
            
        preferred_provider = self.ask_provider(show_info.get('providers'))

        if preferred_provider is None:
            return 0
        try:
            streamseek_handler.download(download_mode, stream.get_name(), preferred_provider, show.get('link'), language, show_type, season, episode)     
        except KeyboardInterrupt:
            self.line(
f"""\
----------------------------------------------------------
--------- Downloads may still be running. ----------------
----------------------------------------------------------

Please don't close this terminal window until it's done.
"""
)

        except Exception as e:self.line(
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

        _list: list[str] = []
        for stream in streams:
            _list.append(stream.get_title())
        _list.append("-- Quit --")

        choice = self.choice(
            "Choose a streaming site:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        # Find stream from choice
        stream = None
        for _stream in streams:
            if _stream.get_title() == choice:
                stream = _stream
                break

        if stream is None:
            self.line("Invalid stream choice")
            return None
        
        return stream

    # Ask and search for show
    def ask_show(self, seek_handler: StreamseekerHandler, show: StreamBase) -> dict:
        search_term = self.ask("Enter show name:")
        self.line("")

        search_term = urllib.parse.quote_plus(search_term)

        results = seek_handler.search_query(show.get_name(), search_term)
        _list: list[str] = []
        for _show in results:
            _list.append(_show.get('name'))
        _list.append("-- Retry search --")
        _list.append("-- Quit --")

        choice = self.choice(
            "Choose a show:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.line("")

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
            self.line("Invalid show choice")
            return None

        return show
    
    def ask_show_type(self, types: Collection[str]) -> str:
        choice = self.choice(
            "Choose a show type:",
            types,
            attempts=3,
            default=len(types) - 1,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice

    def ask_language(self, languages: dict) -> str:
        _list: list[str] = []
        for language in languages.values():
            _list.append(language.get('title'))
        _list.append("-- Quit --")
        
        choice = self.choice(
            "Choose a language:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        for language_key in languages.keys():
            language = languages.get(language_key)
            if language.get('title') == choice:
                return language_key
        
        return None

    def ask_provider(self, providers: dict) -> str:
        _list: list[str] = []
        for provider in providers.values():
            _list.append(provider.get('title'))
        _list.append("-- Quit --")
        
        choice = self.choice(
            "Choose a language:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        for provider_key in providers.keys():
            provider = providers.get(provider_key)
            if provider.get('title') == choice:
                return provider_key
        
        return None
    
    def ask_download_mode(self) -> str:
        choice = self.choice(
            "Choose a download mode:",
            ["All after", "Only one", "-- Quit --"],
            attempts=3,
            default=2,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice

    def ask_number(self, label:str, list: Collection[int]) -> int:
        _list = list.copy()
        _list.insert(0, "-- Quit --")

        if len(_list) == 0:
            return None

        choice = self.choice(
            label,
            _list,
            attempts=3,
            default=0,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        return choice
