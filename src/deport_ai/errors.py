class DeportAIError(Exception):
    """Error esperado y apto para mostrar al usuario."""


class APIError(DeportAIError):
    pass


class TeamNotFoundError(DeportAIError):
    pass


class AmbiguousTeamError(DeportAIError):
    def __init__(self, message: str, candidates: list | None = None) -> None:
        super().__init__(message)
        # Equipos empatados en la búsqueda, para desempatar con el partido programado.
        self.candidates = list(candidates or [])


class InsufficientDataError(DeportAIError):
    pass


class LiveMatchError(DeportAIError):
    """Se lanza cuando un partido ya comenzó o se encuentra en vivo."""
    pass

