from streamseeker.api.core.classes.base_class import BaseClass
from streamseeker.api.core.downloader.helper import DownloadHelper

class StreamBase(BaseClass):
    name = None
    urls = None
    title = {}
    description = {}

    def get_name(self):
        return self.name
    
    def get_urls(self):
        return self.urls

    def get_title(self, language="en"):
        if language in self.title:
            return self.title[language]
        else:
            return f"Error-001"

    def get_description(self, language="en"):
        if language in self.description:
            return self.description[language]
        else:
            return f"Error-001"
        
    def is_downloaded(self, file_path) -> bool:
        helper = DownloadHelper()
        return helper.is_downloaded(file_path)
    
    def download_successfull(self, file_path) -> None:
        helper = DownloadHelper()
        helper.download_success(file_path)
    
    def download_error(self, data, url="") -> None:
        helper = DownloadHelper()
        helper.download_error(data, url)
 
    def build_url(self, name):
        raise NotImplementedError("build_url() must be implemented")

    def search(self, name):
        raise NotImplementedError("search() must be implemented")
    
    def search_query(self, search_term):
        raise NotImplementedError("search_query() must be implemented")
    
    def download(self, name: str, preferred_provider: str, language: str, type: str, season: int, episode: int=0):
        raise NotImplementedError("download() must be implemented")
    
    def search_types(self, name):
        raise NotImplementedError("search_types() must be implemented")
    
    def search_seasons(self, name, type=None):
        raise NotImplementedError("search_seasons() must be implemented")
    
    def search_providers(self, name, type, season, episode=0) -> dict:
        raise NotImplementedError("search_providers() must be implemented")

    def search_episodes(self, name, type, season):
        raise NotImplementedError("search_episodes() must be implemented")
    
    def seach_languages(self, name, type, season=0, episode=0) -> dict:
        raise NotImplementedError("search_languages() must be implemented")
