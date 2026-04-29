import json
import time
from datetime import datetime, timezone

from streamseeker import paths
from streamseeker.api.core.classes.base_class import BaseClass

from streamseeker.api.core.exceptions import ProviderError, LanguageError, DownloadExistsError, LinkUrlError
from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.providers.providers import Providers
from streamseeker.api.streams.streams import Streams
from streamseeker.api.streams.stream_base import StreamBase

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class StreamseekerHandler(BaseClass):
    DEFAULTS = {
        "preferred_provider": "voe",
        "output_folder": "downloads",
        "output_folder_year": False,
        "overwrite": False,
        "max_concurrent": 2,
        "max_retries": 3,
        "ddos_limit": 3,
        "ddos_timer": 90,
        "start_delay_min": 5,
        "start_delay_max": 25,
    }

    def __init__(self, config: dict={}):
        super().__init__()
        self._providers = Providers()
        self._streams = Streams()
        self._manager = DownloadManager()

        # Load config: defaults ← config.json ← passed config
        self.config = dict(self.DEFAULTS)
        file_config = self._load_config_file()
        self.config.update(file_config)
        self.config.update({k: v for k, v in config.items() if v is not None})

        # Resolve output_folder against ~/.streamseeker/ so streams get an absolute path.
        # Keeps the config value user-friendly (relative "downloads") but the runtime
        # value unambiguous regardless of CWD.
        self.config["output_folder"] = str(paths.downloads_dir())

    @classmethod
    def _load_config_file(cls) -> dict:
        config_file = paths.config_file()
        if not config_file.is_file():
            return {}
        try:
            return json.loads(config_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def streams(self):
        streams = self._streams.get_all()
        for stream in streams:
            stream.set_config(self.config)
        return streams

    def providers(self):
        return self._providers.get_all()

    def search(self, stream_name: str, name: str):
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)
        return stream.search(name)

    def search_details(self, stream_name: str, name: str, type: str, season_movie: int=0, episode: int=0):
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)
        return stream.search_details(name, type, season_movie, episode)

    def search_query(self, stream_name: str, search_term: str):
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)
        return stream.search_query(search_term)

    def search_episodes(self, stream_name: str, name: str, type: str, season: int):
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)
        return stream.search_episodes(name, type, season)

    # download_type: [all, only_season, single]
    # stream_name: [aniworldto, sto, ...]
    # preferred_provider: [voe, streamtape, ...]
    # name: [naruto]
    # language: [german, japanese-english, ...]
    # type: [series, movie, ...] stream specific
    # season: [1, 2, 3, ...] (default: 0) Start from
    # episode [1, 2, 3, ...] (default: 0) Start from
    def download(self, download_type: str, stream_name: str, preferred_provider: str, name: str, language: str, type: str, season: int=0, episode: int=0, url: str=None):
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)

        if stream is None:
            return None

        threads = []
        match download_type:
            case "all":
                _threads = self._all_download(stream, preferred_provider, name, language, type, season, episode)
                threads.extend(_threads);
            # case "only_season":
            #     self._season_download(stream, preferred_provider, name, language, type, season, episode)
            case "single":
                try:
                    downloader = stream.download(name, preferred_provider, language, type, season, episode, url=url)
                    if downloader is not None:
                        self._register_context(downloader, stream.get_name(), preferred_provider, name, language, type, season, episode)
                        threads.append(downloader)
                except ProviderError as e:
                    logger.error(f"<error>{e}</error>")
                except LanguageError as e:
                    logger.error(f"{e}")
                except LinkUrlError as e:
                    logger.error(f"{e}")
                except DownloadExistsError as e:
                    from streamseeker.i18n import t
                    logger.error(f"<success>{t('process.already_in_collection')}</success>")
                    pass
            case _:
                return None

        # Threads are tracked by DownloadManager via the downloaders
        pass

    def _all_download(self, stream: StreamBase, preferred_provider: str, name: str, language: str, type: str, season: int, episode: int):
        seasons = stream.search_seasons(name, type)
        if season > 0:
            # remove all seasons before the given season
            seasons = [e for e in seasons if e >= season]

        threads = []
        for _season in seasons:
            sub_threads = self._season_download(stream, preferred_provider, name, language, type, _season, episode)
            episode = 0
            if sub_threads is None:
                continue

            threads.extend(sub_threads)

        return threads

    def _season_download(self, stream: StreamBase, preferred_provider: str, name: str, language: str, type:str, season:int, episode: int=0):
        match type:
            case "staffel":
                episodes = stream.search_episodes(name, type, season)
                if episodes is None:
                    return None
            case _:
                episodes = [0]

        if episode > 0:
            # remove all episodes before the given episode
            episodes = [e for e in episodes if e >= episode]

        threads = []
        for episode in episodes:
            if self.ddos_counter >= self.config.get("ddos_limit"):
                logger.warning(f"DDOS limit reached. Waiting for <warning>{self.config.get('ddos_timer')}</warning> seconds.")
                time.sleep(self.config.get("ddos_timer"))
                self.ddos_counter = 0

            try:
                response = stream.download(name, preferred_provider, language, type, season, episode)
                if response is None:
                    continue
                self._register_context(response, stream.get_name(), preferred_provider, name, language, type, season, episode)
            except ProviderError as e:
                logger.error(f"<error>{e}</error>")
                continue
            except LanguageError as e:
                logger.error(f"{e}")
                continue
            except LinkUrlError as e:
                logger.error(f"{e}")
                continue
            except DownloadExistsError as e:
                continue

            threads.append(response)

            self.ddos_counter += 1

        return threads

    def _register_context(self, downloader, stream_name: str, provider: str, name: str, language: str, type: str, season: int, episode: int):
        """Register download context for retry queue and save to persistent queue."""
        file_name = downloader.file_name
        context = {
            "stream_name": stream_name,
            "provider": provider,
            "name": name,
            "language": language,
            "type": type,
            "season": season,
            "episode": episode,
            "file_name": file_name,
            "added_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }
        self._manager.register_retry_context(file_name, context)
        self._enqueue_item(context)

    def _enqueue_item(self, item: dict) -> None:
        """Route an enqueue to the daemon (if alive) or to the local manager.

        Single-writer rule: when the daemon runs, it must be the only process
        writing to ``download_queue.json``. CLI-side calls therefore delegate
        over HTTP. If the daemon is unreachable, we fall back to a direct local
        enqueue so the CLI keeps working standalone.
        """
        from streamseeker.api.core import daemon_client

        if daemon_client.is_daemon_running():
            try:
                daemon_client.queue_add(
                    stream=item.get("stream_name", ""),
                    slug=item.get("name", ""),
                    type=item.get("type", "staffel"),
                    season=int(item.get("season") or 0),
                    episode=int(item.get("episode") or 0),
                    language=item.get("language", "german"),
                    preferred_provider=item.get("preferred_provider"),
                    file_name=item.get("file_name"),
                )
                return
            except Exception as exc:
                logger.warning(f"daemon enqueue failed, falling back to local: {exc}")
        self._manager.enqueue(item)

    def enqueue_all(self, stream_name: str, preferred_provider: str, name: str, language: str, type: str, season: int = 0, episode: int = 0, seasons_list: list[int] = None, episodes_list: list[int] = None) -> int:
        """Enqueue all episodes from the given season/episode onwards. No downloads started.

        seasons_list/episodes_list: pre-fetched data from the wizard to avoid duplicate HTTP requests.
        """
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)

        if seasons_list is None:
            seasons_list = stream.search_seasons(name, type)
        if season > 0:
            seasons_list = [s for s in seasons_list if s >= season]

        count = 0
        for _season in seasons_list:
            if type == "staffel":
                # Use pre-fetched episodes only for the starting season
                if episodes_list is not None and _season == season:
                    eps = episodes_list
                else:
                    eps = stream.search_episodes(name, type, _season)
                if eps is None:
                    continue
                if episode > 0 and _season == season:
                    eps = [e for e in eps if e >= episode]
            else:
                eps = [_season]

            for _episode in eps:
                file_path = stream.build_file_path(name, type, _season, _episode, language)
                item = {
                    "stream_name": stream_name,
                    "show_name": name,
                    "show_url": name,
                    "preferred_provider": preferred_provider,
                    "name": name,
                    "language": language,
                    "type": type,
                    "season": _season,
                    "episode": _episode,
                    "file_name": file_path,
                    "added_at": datetime.now(timezone.utc).astimezone().isoformat(),
                }
                self._enqueue_item(item)
                count += 1

            episode = 0

        return count

    def enqueue_missing(self, stream_name: str, preferred_provider: str, name: str, language: str, type: str) -> int:
        """Enqueue every episode that is neither downloaded nor already queued.

        "Downloaded" comes from the LibraryStore entry; "queued" from the
        current download queue. Movies (``type == "filme"``) only enqueue if
        not already downloaded/queued.
        """
        from streamseeker.api.core.library.store import LibraryStore, KIND_LIBRARY

        stream = self._streams.get(stream_name)
        stream.set_config(self.config)

        entry = LibraryStore().get(KIND_LIBRARY, f"{stream_name}::{name}") or {}
        downloaded_by_season: dict[int, set[int]] = {}
        for sk, sv in (entry.get("seasons") or {}).items():
            try:
                downloaded_by_season[int(sk)] = set(int(e) for e in (sv.get("downloaded") or []))
            except (TypeError, ValueError):
                continue
        movie_downloaded = bool((entry.get("movies") or {}).get("downloaded"))

        queued: set[tuple[int, int]] = set()
        for q in self._manager.get_queue():
            if q.get("stream_name") != stream_name or q.get("name") != name:
                continue
            try:
                queued.add((int(q.get("season") or 0), int(q.get("episode") or 0)))
            except (TypeError, ValueError):
                continue

        count = 0
        if type == "filme":
            if not movie_downloaded and (0, 0) not in queued:
                count += self.enqueue_single(stream_name, preferred_provider, name, language, type, 0, 0)
            return count

        seasons_list = stream.search_seasons(name, type)
        for season in seasons_list or []:
            # Season 0 on s.to is the Filme-section, on aniworldto specials.
            # "Fehlende Episoden" reasons over real TV seasons; movies
            # should be handled via type=='filme' so we never silently
            # enqueue them here.
            if int(season) == 0:
                continue
            episodes = stream.search_episodes(name, type, season) or []
            already = downloaded_by_season.get(season, set())
            for episode in episodes:
                if episode in already:
                    continue
                if (season, episode) in queued:
                    continue
                self.enqueue_single(stream_name, preferred_provider, name, language, type, season, episode)
                count += 1
        return count

    def enqueue_single(self, stream_name: str, preferred_provider: str, name: str, language: str, type: str, season: int = 0, episode: int = 0, url: str = None) -> int:
        """Enqueue a single download item."""
        stream = self._streams.get(stream_name)
        stream.set_config(self.config)

        file_path = stream.build_file_path(name, type, season, episode, language)
        item = {
            "stream_name": stream_name,
            "show_name": name,
            "show_url": url or name,
            "preferred_provider": preferred_provider,
            "name": name,
            "language": language,
            "type": type,
            "season": season,
            "episode": episode,
            "file_name": file_path,
            "added_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }
        self._enqueue_item(item)
        return 1
