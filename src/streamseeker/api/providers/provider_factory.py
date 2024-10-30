from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.exceptions import ProviderError 
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

class ProviderFactory(metaclass=Singleton):
    _dict = {}

    def __init__(self) -> None:
        self._import_providers()

    def register(self, provider: ProviderBase) -> None:
        self._dict[provider.name.lower()] = provider

    def get(self, name: str) -> ProviderBase:
        if name.lower() in self._dict:
            return self._dict[name.lower()]
        else:
            raise ProviderError(f"Provider {name} is not registered")
        
    def get_all(self):
        return self._dict.values()

    # Load all providers from the providers folder
    def _get_all_folders(self):
        import os
        path = os.path.join(os.path.dirname(__file__))
        return [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    
    def _import_providers(self) -> None:
        import os
        import importlib.util
        import sys
        import inspect

        folders = self._get_all_folders()
        for folder in folders:
            path = os.path.join(os.path.dirname(__file__), folder)
            for file in os.listdir(path):
                if file.endswith(".py") and file != "__init__.py":
                    spec = importlib.util.spec_from_file_location(file, os.path.join(path, file))
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    clsmembers = inspect.getmembers(sys.modules[spec.name], inspect.isclass)
                    # find the class that inherits from ProviderBase
                    for obj in clsmembers:
                        if inspect.isclass(obj[1]) and issubclass(obj[1], (ProviderBase)) and obj[1].__name__ not in ("ProviderBase", "Logger"):
                            self.register(obj[1]())
                            break
