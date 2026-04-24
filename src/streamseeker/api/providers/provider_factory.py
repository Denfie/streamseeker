import json
import os
from datetime import datetime, timezone

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.exceptions import ProviderError
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class ProviderFactory(metaclass=Singleton):
    _dict = {}

    def __init__(self) -> None:
        self._unsupported: dict[str, dict] = self._load_unsupported()
        self._import_providers()

    def register(self, provider: ProviderBase) -> None:
        self._dict[provider.name.lower()] = provider

    def get(self, name: str, source_url: str = None) -> ProviderBase:
        if name.lower() in self._dict:
            return self._dict[name.lower()]
        else:
            self._track_unsupported(name.lower(), source_url)
            raise ProviderError(f"Provider {name} is not registered")

    def get_unsupported(self) -> dict[str, dict]:
        return self._unsupported

    def _track_unsupported(self, name: str, source_url: str = None) -> None:
        """Track an unsupported provider name with count, URLs, and dates."""
        now = datetime.now(timezone.utc).astimezone().isoformat()
        if name in self._unsupported:
            self._unsupported[name]["count"] += 1
            self._unsupported[name]["last_seen"] = now
            # Add URL if not already tracked
            if source_url:
                urls = self._unsupported[name].setdefault("urls", [])
                if source_url not in urls:
                    urls.append(source_url)
        else:
            self._unsupported[name] = {
                "count": 1,
                "first_seen": now,
                "last_seen": now,
                "urls": [source_url] if source_url else [],
            }
            logger.debug(f"New unsupported provider detected: {name}")
        self._save_unsupported()

    def _load_unsupported(self) -> dict:
        unsupported_file = paths.unsupported_providers_file()
        if not unsupported_file.is_file():
            return {}
        try:
            return json.loads(unsupported_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_unsupported(self) -> None:
        unsupported_file = paths.unsupported_providers_file()
        unsupported_file.parent.mkdir(parents=True, exist_ok=True)
        unsupported_file.write_text(json.dumps(self._unsupported, indent=2, ensure_ascii=False))
        
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
