import enum


class Scope(enum.IntEnum):
    APP = enum.auto
    REQUEST = enum.auto
    ACTION = enum.auto
    STEP = enum.auto
