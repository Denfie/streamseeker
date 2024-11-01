class CacheUrlError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class ProviderError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class LanguageError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class ContinueLoopError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class DownloadError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class DownloadExistsError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)