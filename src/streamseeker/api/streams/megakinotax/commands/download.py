import html
import urllib.parse

from cleo.commands.command import Command

from streamseeker.api.handler import StreamseekerHandler
from streamseeker.api.streams.stream_base import StreamBase
from streamseeker.api.core.request_handler import RequestHandler

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class MegakinotaxDownloadCommand:
    def __init__(self, cli: Command, stream: StreamBase):
        self.cli = cli
        self.stream = stream

    def handle(self) -> int:
        streamseek_handler = StreamseekerHandler()

        movie = self.ask_movie()

        if movie is None:
            return 0

        from streamseeker.api.core.downloader.processor import QueueProcessor

        streamseek_handler.enqueue_single(
            self.stream.get_name(), 'voe', movie.get('name'),
            'de', 'movie', 0, 0, url=movie.get('href')
        )
        from streamseeker.i18n import t
        self.cli.line(f"<info>{t('queue.added.singular', count=1)}</info>")

        QueueProcessor().start(config=streamseek_handler.config)

        return 0

    def ask_movie(self) -> dict:
        search_term = self.cli.ask("Enter movie name:")
        self.cli.line("")

        search_term = urllib.parse.quote_plus(search_term)
        results = self.stream.search_query(search_term)

        request_handler = RequestHandler()
        soup = request_handler.soup(results['html'])

        movies = []
        for element in soup.findAll('a', class_="poster"):
            href = str(element.get("href", ""))
            title = str(element.find("h3", class_="poster__title").text)
            description = str(element.find("div", class_="poster__text").text)
            movies.append({
                "name": title,
                "description": description,
                "href": href
            })

        _list: list[str] = []
        for term in movies:
            term['name'] = html.unescape(term.get('name'))
            _list.append(term.get('name'))
        _list.append("-- Retry search --")
        _list.append("-- Quit --")

        choice = self.cli.choice(
            "Choose a movie:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.cli.line("")

        if choice == "-- Quit --":
            return None
        
        if choice == "-- Retry search --":
            return self.ask_movie()

        # Find stream from choice
        movie = None
        for term in movies:
            if term.get('name') == choice:
                movie = term
                break

        if movie is None:
            self.cli.line("Invalid movie choice")
            return None

        return movie
    
    def ask_provider(self) -> dict:
        pass