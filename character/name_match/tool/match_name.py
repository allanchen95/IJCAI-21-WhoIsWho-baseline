import copy
from .util import *
from .is_chinese import is_chinese_name
import itertools

black_list = []
funcs = [
    match_name_one,
    match_name_two,
    match_name_three,
    match_name_four,
    match_name_five,
    match_name_six,
    match_name_seven,
]


def dryRun(names):
    if len(names) <= 1:
        return True

    len_of_most_complex_names, most_complex_names = len(
        next(iter(names)).split()), set()

    for name in names:
        length = len(name.split())
        if length == len_of_most_complex_names:
            most_complex_names.add(name)
        elif length > len_of_most_complex_names:
            len_of_most_complex_names = length
            most_complex_names = set((name, ))

    ## 验证 most_complex_names
    for a, b in itertools.combinations(most_complex_names, 2):
        if not may_be_duplicates_partial(a, b, True):
            return False

    ## 验证剩余的name
    for name in names:
        if name in most_complex_names:
            continue
        passed = False
        for complex_name in most_complex_names:
            if may_be_duplicates_partial(name, complex_name, True):
                passed = True
                break
        if not passed:
            return False
    return True


##  'b u mcneely'   'Betty U. Mcneely'


def match_name(funcs, pnames, anames, name2clean, loose=False):
    filter_pnames = []
    for each in pnames:
        if each not in black_list:
            filter_pnames.append(each)

    if len(filter_pnames) == 0:        
        return [], []
    
    pt = set()
    for each in filter_pnames:
        # pt.add(name)
        name_l = name2clean[each]
        for dname in anames:
            if dname in black_list or dname in pt:
                continue
            dname_l = name2clean[dname]
            is_match = False
            for f in funcs:
                if f(name_l, dname_l, loose):
                    pt.add(dname)
                    is_match = True
                    break
    pt = [name2clean[a] for a in pt]
    pt = set(pt)
    return pt
