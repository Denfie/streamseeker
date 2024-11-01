import json

# from cleo.commands.command import Command

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.request_handler import RequestHandler

class BaseClass(metaclass=Singleton):
    config = {}
    requests = {}

    def set_config(self, config):
        self.config = config

    def set_request(self, name, request):
        self.requests[name] = request

    def get_request(self, name):
        if name not in self.requests:
            return None
        return self.requests[name]
    
    def request(self, url, headers=None):
        response = self.get_request(url)

        if response is None:
            request = RequestHandler()
            response = request.get(url, headers)
            if(response is None):
                return None
            
            dict = {
                "referer": response.url,
                "headers": response.headers,
                "plain_html": response.read(),
                "html": response.read().decode("utf-8")
            }
            self.set_request(url, dict)
            return dict
    
        return response
    
    def request_json(self, url, headers=None):
        response = self.get_request(url)

        if response is None:
            request = RequestHandler()
            response = request.get(url, headers)
            if(response is None):
                return None
            
            dict = {
                "referer": response.url,
                "headers": response.headers,
                "json": json.loads(response.read())
            }
            self.set_request(url, dict)
            return dict
    
        return response
    