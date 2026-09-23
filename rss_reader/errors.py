"""Expected feed failures; messages are safe to display to users."""


class FeedFetchError(Exception):
    pass


class FeedTimeoutError(FeedFetchError):
    pass


class UnsafeFeedURLError(FeedFetchError):
    pass


class InvalidFeedError(FeedFetchError):
    pass
