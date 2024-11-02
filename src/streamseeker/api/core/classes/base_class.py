import json

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.request_handler import RequestHandler

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

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
            
            plain_html = response.read()
            dict = {
                "referer": response.url,
                "headers": response.headers,
                "plain_html": plain_html,
                "html": plain_html.decode("utf-8")
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
            
            plain_html = response.read()
            dict = {
                "referer": response.url,
                "headers": response.headers,
                "json": json.loads(plain_html)
            }
            self.set_request(url, dict)
            return dict
    
        return response
    
    def post_request(self, url, data, headers=None):
        request = RequestHandler()
        response = request.post(url, data, headers)

        if(response is None):
            return None
        
        plain_html = response.read()
        dict = {
            "referer": response.url,
            "headers": response.headers,
            "plain_html": plain_html,
            "html": plain_html.decode("utf-8")
        }
        self.set_request(url, dict)
        return dict