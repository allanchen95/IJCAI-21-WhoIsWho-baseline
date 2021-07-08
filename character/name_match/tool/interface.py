from .match_name import match_name, funcs


def MatchName(name, name_alias, name2clean,loose=False):
    return match_name(funcs, name, name_alias, name2clean, loose)
