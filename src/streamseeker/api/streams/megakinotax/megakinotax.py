import os
import re

from cleo.commands.command import Command

from streamseeker.api.streams.stream_base import StreamBase
from streamseeker.api.providers.provider_factory import ProviderFactory
from streamseeker.api.core.exceptions import ProviderError, LanguageError, DownloadExistsError
from streamseeker.api.core.request_handler import RequestHandler

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class MegakinotaxStream(StreamBase):
    name = "megakinotax"
    urls = ["https://megakino.tax"]
    title = {
        "de": "<fg=magenta>MegaKino.tax</>: Suche nach einem Kinofilm",
        "en": "<fg=magenta>MegaKino.tax</>: Search for an cinema movie"
    }
    description = {
        "de": "Wenn du nach einem Kinofilm suchen möchtest, gib bitte den Namen des Films ein.",
        "en": "If you want to search for a cinema movie, please enter the name of the movie you want to search for."
    }

    def __init__(self):
        super().__init__()
        self._provider_factory = ProviderFactory()

    def cli(self, cli: Command, cli_type: str="download"):
        if cli_type == "download":
            from streamseeker.api.streams.megakinotax.commands.download import MegakinotaxDownloadCommand
            command = MegakinotaxDownloadCommand(cli, self)
            return command.handle()
        else:
            raise ValueError(f"Command {cli_type} is not supported")

    # Search for the movie
    # name: name of the movie
    def search(self, name):
        return {
            "types": ['filme'],
            "languages": {
                "de": {
                    "key": "de",
                    "title": "Deutsch"
                },
            }
        }
    
    def search_query(self, search_term):
        search_url = f"{self.urls[0]}"
        request = self.post_request(search_url, {"do": "search", "subaction": "search", "story": search_term})

        return request
    
    def search_details(self, name, type, season_movie, episode):
        dict = {
            "providers": {
                "voe": {
                    "key": "voe",
                    "title": "VOE"
                }
            },
            "languages": {
                "de": {
                    "key": "de",
                    "title": "Deutsch"
                },
            }
        }
        return dict
    
    # Download the movie
    # name: name of the movie
    # preferred_provider: provider of the movie [voe, streamtape, ...]
    # language: language of the movie
    # type: type of the movie [filme, staffel]
    # season: season of the movie
    # episode: episode of the movie (default=0)
    # rule: rule to download the movie [all, only_season, only_episode] (default=all)
    def download(self, name: str, preferred_provider: str="voe", language: str="de", type: str="movie", season: int=0, episode: int=0, url: str=None):
        output_struct = [self.config.get("output_folder"), "movies", "megakinotax"]
        file_name = f"{name}-movie-{language}.mp4"
        output_struct.append(file_name) 
        output_file = os.sep.join(output_struct)

        request_url = self._get_redirect_url(url)
        provider_voe = self._provider_factory.get("voe")

        try:
            return provider_voe.download(request_url, output_file)
        except ProviderError:
            logger.error(f"<fg=yellow>Provider 'VOE' failed</>")  

        self.download_error(f"[{self.name}::{language}::{preferred_provider}]", request_url)
        raise ProviderError
    
    def _get_redirect_url(self, url):
        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        link = soup.find('iframe', {"id": "film_main"})
        redirect_url = link.get('data-src')

        return redirect_url