import os
import re

from streamseeker.api.streams.stream_base import StreamBase
from streamseeker.api.providers.provider_factory import ProviderFactory
from streamseeker.api.core.exceptions import ProviderError, LanguageError, DownloadExistsError
from streamseeker.api.core.request_handler import RequestHandler

class AniworldtoStream(StreamBase):
    name = "aniworldto"
    urls = ["https://aniworld.to"]
    title = {
        "de": "Suche nach einem Anime",
        "en": "Search for an anime"
    }
    description = {
        "de": "Wenn du nach einem Anime suchen möchtest, gib bitte den Namen des Animes ein.",
        "en": "If you want to search for an anime, please enter the name of the anime you want to search for."
    }

    def __init__(self):
        super().__init__()
        self._provider_factory = ProviderFactory()

    # Build the url for the anime
    # name: name of the anime
    def build_url(self, name, default_url=0):
        return f"{self.urls[default_url]}/anime/stream/{name}"

    # Search for the anime
    # name: name of the anime
    def search(self, name):
        types = self.search_types(name)
        movies = []
        series = []

        if "filme" in types:
            movies = self.search_seasons(name, "filme")

        if "staffel" in types:
            series = self.search_seasons(name, "staffel")

        if len(series) == 0 and len(movies) == 0:
            return None
        
        episode = 0
        if len(series) == 0:
            type = "filme"
            season = movies[0]
        else:
            type = "staffel"
            season = series[0]
            episodes = self.search_episodes(name, type, season)
            episode = episodes[0]

        providers = self.search_providers(name, type, season, episode)
        languages = self.seach_languages(name, type, season, episode)
        dict = {
            "types": types,
            "movies": movies,
            "series": series,
            "providers": providers,
            "languages": languages
        }
        return dict
    
    def search_query(self, search_term):
        search_url = f"{self.urls[0]}/ajax/seriesSearch?keyword={search_term}"

        request = self.request_json(search_url)

        if request.get('json') is None:
            return None

        return request.get('json')
    
    # Download the anime
    # name: name of the anime
    # preferred_provider: provider of the anime [voe, streamtape, ...]
    # language: language of the anime
    # type: type of the anime [filme, staffel]
    # season: season of the anime
    # episode: episode of the anime (default=0)
    # rule: rule to download the anime [all, only_season, only_episode] (default=all)
    def download(self, name: str, preferred_provider: str, language: str, type: str, season: int, episode: int=0):
        site_url = self.build_url(name)

        output_struct = [self.config.get("output_folder"), "anime", name]
        match type:
            case "filme":
                url = f"{site_url}/filme/film-{season}"
                file_name = f"{name}-movie-{season}-{language}.mp4"
                output_struct.append("movies")
            case "staffel":
                url = f"{site_url}/staffel-{season}/episode-{episode}"
                output_struct.append(f"Season {season}")
                file_name = f"{name}-s{season}e{episode}-{language}.mp4"
            case _:
                raise ValueError(f"Type {type} is not supported")
            
        languages = self.seach_languages(name, type, season, episode)

        if languages is not None and languages.get(language) is None:
            self.line(f"<fg=red>Language {language} is not available for {name} -> {url}</>")

        if self.config.get("output_folder_year"):
            year = self._get_year(url)
            if year is not None:
                output_struct.append(year)

        output_struct.append(file_name) 
        output_file = os.sep.join(output_struct)

        if self.is_downloaded(output_file):
            raise DownloadExistsError(f"File {output_file} already exists")
        
        providers = self.search_providers(name, type, season, episode)

        if preferred_provider not in providers:
            self.line(f"<fg=red>Provider {preferred_provider} is not available</>")
        else:
            temp_provider = providers.get(preferred_provider)
            providers.pop(preferred_provider)
            dummy = {}
            dummy[preferred_provider] = temp_provider
            providers = {**dummy, **providers}

        for provider_key in providers.keys():
            provider = providers.get(provider_key)

            # self.line(f"<info>Trying {provider.get('title')}</info>")

            try:
                language_key = languages.get(language).get("key")
                redirect_url = self._get_redirect_url(url, language_key, provider.get("title"))

                # Starts redirect_url not with http
                if not redirect_url.startswith("http"):
                    redirect_url = f"{self.urls[0]}{redirect_url}"
            except LanguageError:
                self.download_error(f"[{language}::{provider_key}]", url)
                raise LanguageError
                 
            try:
                provider_class = self._provider_factory.get(provider_key)
                provider_class.set_config(self.config)
                # self.line(f"<fg=red>Provider {provider.get('title')} - File {output_file} added to queue.</>")
                return provider_class.download(redirect_url, output_file)
            except ProviderError:
                self.line(f"<fg=yellow>Provider '{provider.get('title')}' failed. Try next provider in list.</>")  
                continue
        
        self.line(f"<fg=yellow>No provider works for {output_file}.</>") 
        self.download_error(f"[{language}::{preferred_provider}]", url)
        raise ProviderError
    
    # Search for the types of the anime
    # name: name of the anime
    def search_types(self, name):
        url = self.build_url(name)

        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        return_array = []
        pattern = re.compile(r"/anime/stream/(?P<name>.*)/(?P<type>.*)", re.M)

        for element in soup.findAll('a'):
            href = str(element.get("href", ""))
            search = pattern.search(href)
            if search is None:
                continue
            found_name = search.group('name').lower()
            found_type = search.group('type').lower()
            if(found_name == name):
                if found_type == 'filme':
                    type = 'filme'
                else:
                    type = 'staffel'

                if type not in return_array:
                    return_array.append(type)

        return return_array

    # Search for the seasons of the anime
    # name: name of the anime
    # type: type of the anime [filme, staffel] (default=staffel)
    def search_seasons(self, name, type="staffel"):
        url = self.build_url(name)

        url = f"{url}"
        if type == "filme":
            url = f"{url}/filme"

        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        match type:
            case "filme":
                pattern = re.compile(r"/anime/stream/(?P<name>.*)/filme/film-(?P<count>\d+)", re.M)
            case "staffel":
                pattern = re.compile(r"/anime/stream/(?P<name>.*)/staffel-(?P<count>\d+)", re.M)
            case _:
                raise ValueError(f"Type {type} is not supported")
            
        return_array = []
        for element in soup.findAll('a'):
            search = pattern.search(element.get("href", ""))
            if search is None:
                continue
            found_name = search.group('name').lower()
            count = int(search.group('count'))
            if found_name == name and count not in return_array:
                return_array.append(count)
        
        return return_array
    
    # Search for the providers of the anime
    # name: name of the anime
    # type: type of the anime [filme, staffel]
    # season: season of the anime
    # episode: episode of the anime (default=0)
    def search_providers(self, name, type, season, episode=0) -> dict: 
        url = self.build_url(name)

        match type:
            case "filme":
                url = f"{url}/filme/film-{season}"
            case "staffel":
                if(episode > 0):
                    url = f"{url}/staffel-{season}/episode-{episode}"
                else:
                    url = f"{url}/staffel-{season}/episode-1"
            case _:
                raise ValueError(f"Type {type} is not supported")

        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        dict = {}
        check_array = []
        pattern = re.compile(r"Hoster (?P<provider>.*)", re.M)
        for element in soup.findAll('i'):
            title = str(element.get("title", ""))
            search = pattern.search(title)
            if search is None:
                continue
            provider = search.group('provider').lower()
            if provider not in check_array:
                try:
                    provider_obj = self._provider_factory.get(provider)
                except ProviderError:
                    continue
                dict[provider] = {
                    "title": search.group('provider'),
                    "priority": provider_obj.get_priority()
                }
                check_array.append(provider)
        # Sort the dictionary by priority
        dict = {k: v for k, v in sorted(dict.items(), key=lambda item: item[1]['priority'])}
        return dict
    
    # Search for the episodes of the anime
    # name: name of the anime
    # type: type of the anime [filme, staffel]
    # season: season of the anime
    def search_episodes(self, name, type, season):
        url = self.build_url(name)

        match type:
            case "filme":
                raise ValueError(f"Type {type} does not have episodes")
            case "staffel":
                url = f"{url}/staffel-{season}"
                pattern = re.compile(r"/anime/stream/(?P<name>.*)/staffel-(?P<seasonCount>\d+)/episode-(?P<episodeCount>\d+)", re.M)
            case _:
                raise ValueError(f"Type {type} is not supported")
        
        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])
            
        return_array = []
        for element in soup.findAll('a'):
            search = pattern.search(element.get("href", ""))
            if search is None:
                continue

            found_name = search.group('name').lower()
            season_count = int(search.group('seasonCount'))

            episode_count = int(search.group('episodeCount'))

            if episode_count not in return_array:
                return_array.append(episode_count)
        
        return return_array

    # Search for the languages of the anime
    # name: name of the anime
    # type: type of the anime [filme, staffel]
    # season: season of the anime (default=0)
    # episode: episode of the anime (default=0)
    def seach_languages(self, name, type, season=0, episode=0) -> dict:
        url = self.build_url(name)
        default_season = 1
        default_episode = 1

        if season != 0:
            default_season = season
        if episode != 0:
            default_episode = episode

        match type:
            case "filme":
                url = f"{url}/filme/film-{default_season}"
            case "staffel":
                url = f"{url}/staffel-{season}/episode-{default_episode}"
            case _:
                raise ValueError(f"Type {type} is not supported")

        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        change_language_div = soup.find("div", class_="changeLanguageBox")

        if change_language_div is None:
            return None

        dict = {}
        check_array = []
        pattern_src = re.compile(r"/.*/(?P<language>.*)\.svg", re.M)
            
        for element in change_language_div.find_all('img'):
            src = str(element.get("src", ""))
            search = pattern_src.search(src)
            if search is None:
                continue
            language = search.group('language').lower()
            if language not in check_array:
                check_array.append(language)
                dict[language] = {
                    "key": element.get("data-lang-key", ""),
                    "title": element.get("title", "")
                }
        return dict
    
    def _get_redirect_url(self, url, language_key, provider):
        request = self.request(url)
        request_handler = RequestHandler()
        soup = request_handler.soup(request['plain_html'])

        links = soup.findAll('li', {"data-lang-key": language_key})

        if len(links) == 0:
            return None
        
        for link in links:
            # Find a tag that contains an i tag with the title "Hoster {provider}"
            if link.find('i', title=f"Hoster {provider}") is not None:
                redirect_url = link.find('a').get('href')
                return redirect_url
            
        raise LanguageError
    
    def _get_year(self, url):
        """
        Get the year of the show.

        Parameters:
            url (String): url of the show.

        Returns:
            year (String): year of the show.
        """
        try:
            request = self.request(url)
            request_handler = RequestHandler()
            soup = request_handler.soup(request['plain_html'])
            year = soup.find("span", {"itemprop": "startDate"}).text
            return year
        except AttributeError:
            self.line("<fg=red>Could not find year of the show.</>")
            return None