import enum


class Scope(enum.IntEnum):
    APP = 1
    REQUEST = 2
    ACTION = 3
    STEP = 4
