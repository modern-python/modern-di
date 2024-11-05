import enum


class Scope(enum.IntEnum):
    APP = 1
    SESSION = 2
    REQUEST = 3
    ACTION = 4
    STEP = 5
