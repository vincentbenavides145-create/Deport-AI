class DeportAIError(Exception):
    """Error esperado y apto para mostrar al usuario."""


class APIError(DeportAIError):
    pass


class TeamNotFoundError(DeportAIError):
    pass


class AmbiguousTeamError(DeportAIError):
    pass


class InsufficientDataError(DeportAIError):
    pass


class LiveMatchError(DeportAIError):
    """Se lanza cuando un partido ya comenzó o se encuentra en vivo."""
    pass

