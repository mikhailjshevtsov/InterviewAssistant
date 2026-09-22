from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class MenuAction(StrEnum):
    PREPARE = "prepare"
    HELP = "help"
    MAIN_MENU = "main"


class MenuCallback(CallbackData, prefix="menu"):
    action: MenuAction
