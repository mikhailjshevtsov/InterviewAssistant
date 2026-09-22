class DatabaseError(Exception):
    """Technical storage failure; details are logged, not shown to users."""


class EntityNotFoundError(DatabaseError):
    pass
