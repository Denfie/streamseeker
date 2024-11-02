from __future__ import annotations

import html
import urllib.parse

from streamseeker.api.handler import StreamseekerHandler
from streamseeker.api.streams.stream_base import StreamBase
from cleo.commands.command import Command

class DownloadCommand(Command):
    name = "download"
    description = "Start interactive mode to download a show."

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata

        streamseek_handler = StreamseekerHandler()

        stream = self.ask_stream(streamseek_handler)

        if stream is None:
            return 0
        
        return stream.cli(self, "download")

    # Ask for streaming provider
    def ask_stream(self, seek_handler: StreamseekerHandler) -> StreamBase:
        streams = seek_handler.streams()

        if len(streams) == 0:
            return None
        
        if len(streams) == 1:
            return streams[0]

        _list: list[str] = []
        for stream in streams:
            _list.append(stream.get_title())
        _list.append("-- Quit --")

        choice = self.choice(
            "Choose a streaming site:",
            _list,
            attempts=3,
            default=len(_list) - 1,
        )
        self.line("")

        if(choice == "-- Quit --"):
            return None
        
        # Find stream from choice
        stream = None
        for _stream in streams:
            if _stream.get_title() == choice:
                stream = _stream
                break

        if stream is None:
            self.line("Invalid stream choice")
            return None
        
        return stream
