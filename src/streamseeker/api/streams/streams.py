from streamseeker.api.streams.stream_factory import StreamFactory

class Streams:
    def __init__(self) -> None:
        self._stream_factory = StreamFactory()

    def get(self, name: str):
        return self._stream_factory.get(name)
    
    def get_all(self):
        return self._stream_factory.get_all()