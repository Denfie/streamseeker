from streamseeker.api.providers.provider_factory import ProviderFactory

class Providers:
    def __init__(self) -> None:
        self._provider_factory = ProviderFactory()

    def get(self, name: str):
        return self._provider_factory.get(name)
    
    def get_all(self):
        return self._provider_factory.get_all()