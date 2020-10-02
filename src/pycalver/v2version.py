# This file is part of the pycalver project
# https://github.com/mbarkhau/pycalver
#
# Copyright (c) 2018-2020 Manuel Barkhau (mbarkhau@gmail.com) - MIT License
# SPDX-License-Identifier: MIT
"""Functions related to version string manipulation."""

import typing as typ
import logging
import datetime as dt

import lexid

from . import version
from . import v2patterns

logger = logging.getLogger("pycalver.v2version")


CalInfo = typ.Union[version.V2CalendarInfo, version.V2VersionInfo]


def _is_cal_gt(left: CalInfo, right: CalInfo) -> bool:
    """Is left > right for non-None fields."""

    lvals = []
    rvals = []
    for field in version.V2CalendarInfo._fields:
        lval = getattr(left , field)
        rval = getattr(right, field)
        if not (lval is None or rval is None):
            lvals.append(lval)
            rvals.append(rval)

    return lvals > rvals


def _ver_to_cal_info(vinfo: version.V2VersionInfo) -> version.V2CalendarInfo:
    return version.V2CalendarInfo(
        vinfo.year_y,
        vinfo.year_g,
        vinfo.quarter,
        vinfo.month,
        vinfo.dom,
        vinfo.doy,
        vinfo.week_w,
        vinfo.week_u,
        vinfo.week_v,
    )


def cal_info(date: dt.date = None) -> version.V2CalendarInfo:
    """Generate calendar components for current date.

    >>> import datetime as dt

    >>> c = cal_info(dt.date(2019, 1, 5))
    >>> (c.year_y, c.quarter, c.month, c.dom, c.doy, c.week_w, c.week_u, c.week_v)
    (2019, 1, 1, 5, 5, 0, 0, 1)

    >>> c = cal_info(dt.date(2019, 1, 6))
    >>> (c.year_y, c.quarter, c.month, c.dom, c.doy, c.week_w, c.week_u, c.week_v)
    (2019, 1, 1, 6, 6, 0, 1, 1)

    >>> c = cal_info(dt.date(2019, 1, 7))
    >>> (c.year_y, c.quarter, c.month, c.dom, c.doy, c.week_w, c.week_u, c.week_v)
    (2019, 1, 1, 7, 7, 1, 1, 2)

    >>> c = cal_info(dt.date(2019, 4, 7))
    >>> (c.year_y, c.quarter, c.month, c.dom, c.doy, c.week_w, c.week_u, c.week_v)
    (2019, 2, 4, 7, 97, 13, 14, 14)
    """
    if date is None:
        date = version.TODAY

    kwargs = {
        'year_y' : date.year,
        'year_g' : int(date.strftime("%G"), base=10),
        'quarter': version.quarter_from_month(date.month),
        'month'  : date.month,
        'dom'    : date.day,
        'doy'    : int(date.strftime("%j"), base=10),
        'week_w' : int(date.strftime("%W"), base=10),
        'week_u' : int(date.strftime("%U"), base=10),
        'week_v' : int(date.strftime("%V"), base=10),
    }

    return version.V2CalendarInfo(**kwargs)


VALID_FIELD_KEYS = set(version.V2VersionInfo._fields) | {'version'}

MaybeInt = typ.Optional[int]

FieldKey      = str
MatchGroupKey = str
MatchGroupStr = str

PatternGroups = typ.Dict[FieldKey, MatchGroupStr]
FieldValues   = typ.Dict[FieldKey, MatchGroupStr]

VersionInfoKW = typ.Dict[str, typ.Union[str, int, None]]


def _parse_version_info(field_values: FieldValues) -> version.V2VersionInfo:
    """Parse normalized V2VersionInfo from groups of a matched pattern.

    >>> vinfo = _parse_version_info({'year_y': "2018", 'month': "11", 'bid': "0099"})
    >>> (vinfo.year_y, vinfo.month, vinfo.quarter, vinfo.bid, vinfo.tag)
    (2018, 11, 4, '0099', 'final')

    >>> vinfo = _parse_version_info({'year_y': "2018", 'doy': "11", 'bid': "099", 'tag': "beta"})
    >>> (vinfo.year_y, vinfo.month, vinfo.dom, vinfo.doy, vinfo.bid, vinfo.tag)
    (2018, 1, 11, 11, '099', 'beta')

    >>> vinfo = _parse_version_info({'year_y': "2018", 'month': "6", 'dom': "15"})
    >>> (vinfo.year_y, vinfo.month, vinfo.dom, vinfo.doy)
    (2018, 6, 15, 166)

    >>> vinfo = _parse_version_info({'major': "1", 'minor': "23", 'patch': "45"})
    >>> (vinfo.major, vinfo.minor, vinfo.patch)
    (1, 23, 45)

    >>> vinfo = _parse_version_info({'major': "1", 'minor': "023", 'patch': "0045"})
    >>> (vinfo.major, vinfo.minor, vinfo.patch)
    (1, 23, 45)

    >>> vinfo = _parse_version_info({'year_y': "2021", 'week_w': "02"})
    >>> (vinfo.year_y, vinfo.week_w)
    (2021, 2)
    >>> vinfo = _parse_version_info({'year_y': "2021", 'week_u': "02"})
    >>> (vinfo.year_y, vinfo.week_u)
    (2021, 2)
    >>> vinfo = _parse_version_info({'year_g': "2021", 'week_v': "02"})
    >>> (vinfo.year_g, vinfo.week_v)
    (2021, 2)

    >>> vinfo = _parse_version_info({'year_y': "2021", 'month': "01", 'dom': "03"})
    >>> (vinfo.year_y, vinfo.month, vinfo.dom, vinfo.tag)
    (2021, 1, 3, 'final')
    >>> (vinfo.year_y, vinfo.week_w, vinfo.year_y, vinfo.week_u,vinfo.year_g, vinfo.week_v)
    (2021, 0, 2021, 1, 2020, 53)
    """
    for key in field_values:
        assert key in VALID_FIELD_KEYS, key

    fvals = field_values
    tag   = fvals.get('tag'  ) or ""
    pytag = fvals.get('pytag') or ""

    if tag and not pytag:
        pytag = version.PEP440_TAG_BY_RELEASE[tag]
    elif pytag and not tag:
        tag = version.RELEASE_BY_PEP440_TAG[pytag]

    if not tag:
        tag = "final"

    date: typ.Optional[dt.date] = None

    year_y: MaybeInt = int(fvals['year_y']) if 'year_y' in fvals else None
    year_g: MaybeInt = int(fvals['year_g']) if 'year_g' in fvals else None

    month: MaybeInt = int(fvals['month']) if 'month' in fvals else None
    doy  : MaybeInt = int(fvals['doy'  ]) if 'doy' in fvals else None
    dom  : MaybeInt = int(fvals['dom'  ]) if 'dom' in fvals else None

    week_w: MaybeInt = int(fvals['week_w']) if 'week_w' in fvals else None
    week_u: MaybeInt = int(fvals['week_u']) if 'week_u' in fvals else None
    week_v: MaybeInt = int(fvals['week_v']) if 'week_v' in fvals else None

    if year_y and doy:
        date  = version.date_from_doy(year_y, doy)
        month = date.month
        dom   = date.day
    else:
        month = int(fvals['month']) if 'month' in fvals else None
        dom   = int(fvals['dom'  ]) if 'dom' in fvals else None

    if year_y and month and dom:
        date = dt.date(year_y, month, dom)

    if date:
        # derive all fields from other previous values
        year_y = int(date.strftime("%Y"), base=10)
        year_g = int(date.strftime("%G"), base=10)
        month  = int(date.strftime("%m"), base=10)
        dom    = int(date.strftime("%d"), base=10)
        doy    = int(date.strftime("%j"), base=10)
        week_w = int(date.strftime("%W"), base=10)
        week_u = int(date.strftime("%U"), base=10)
        week_v = int(date.strftime("%V"), base=10)

    quarter = int(fvals['quarter']) if 'quarter' in fvals else None
    if quarter is None and month:
        quarter = version.quarter_from_month(month)

    # NOTE (mb 2020-09-18): If a part is optional, fvals[<field>] may be None
    major = int(fvals.get('major') or 0)
    minor = int(fvals.get('minor') or 0)
    patch = int(fvals.get('patch') or 0)
    num   = int(fvals.get('num'  ) or 0)
    bid   = fvals['bid'] if 'bid' in fvals else "1000"

    vinfo = version.V2VersionInfo(
        year_y=year_y,
        year_g=year_g,
        quarter=quarter,
        month=month,
        dom=dom,
        doy=doy,
        week_w=week_w,
        week_u=week_u,
        week_v=week_v,
        major=major,
        minor=minor,
        patch=patch,
        num=num,
        bid=bid,
        tag=tag,
        pytag=pytag,
    )
    return vinfo


def parse_version_info(
    version_str: str, raw_pattern: str = "vYYYY0M.BUILD[-RELEASE]"
) -> version.V2VersionInfo:
    """Parse normalized V2VersionInfo.

    >>> vinfo = parse_version_info("v201712.0033-beta", raw_pattern="vYYYY0M.BUILD[-RELEASE]")
    >>> fvals = {'year_y': 2017, 'month': 12, 'bid': "0033", 'tag': "beta"}
    >>> assert vinfo == _parse_version_info(fvals)

    >>> vinfo = parse_version_info("v201712.0033", raw_pattern="vYYYY0M.BUILD[-RELEASE]")
    >>> fvals = {'year_y': 2017, 'month': 12, 'bid': "0033"}
    >>> assert vinfo == _parse_version_info(fvals)

    >>> vinfo = parse_version_info("201712.33b0", raw_pattern="YYYY0M.BLD[PYTAGNUM]")
    >>> fvals = {'year_y': 2017, 'month': 12, 'bid': "33", 'tag': "beta", 'num': 0}
    >>> assert vinfo == _parse_version_info(fvals)

    >>> vinfo = parse_version_info("1.23.456", raw_pattern="MAJOR.MINOR.PATCH")
    >>> fvals = {'major': "1", 'minor': "23", 'patch': "456"}
    >>> assert vinfo == _parse_version_info(fvals)
    """
    pattern = v2patterns.compile_pattern(raw_pattern)
    match   = pattern.regexp.match(version_str)
    if match is None:
        err_msg = (
            f"Invalid version string '{version_str}' "
            f"for pattern '{raw_pattern}'/'{pattern.regexp.pattern}'"
        )
        raise version.PatternError(err_msg)
    elif len(match.group()) < len(version_str):
        err_msg = (
            f"Incomplete match '{match.group()}' for version string '{version_str}' "
            f"with pattern '{raw_pattern}'/'{pattern.regexp.pattern}'"
        )
        raise version.PatternError(err_msg)
    else:
        field_values = match.groupdict()
        return _parse_version_info(field_values)


def is_valid(version_str: str, raw_pattern: str = "vYYYY0M.BUILD[-RELEASE[NUM]]") -> bool:
    """Check if a version matches a pattern.

    >>> is_valid("v201712.0033-beta", raw_pattern="vYYYY0M.BUILD[-RELEASE[NUM]]")
    True
    >>> is_valid("v201712.0033-beta", raw_pattern="MAJOR.MINOR.PATCH")
    False
    >>> is_valid("1.2.3", raw_pattern="MAJOR.MINOR.PATCH")
    True
    >>> is_valid("v201712.0033-beta", raw_pattern="MAJOR.MINOR.PATCH")
    False
    """
    try:
        parse_version_info(version_str, raw_pattern)
        return True
    except version.PatternError:
        return False


TemplateKwargs = typ.Dict[str, typ.Union[str, int, None]]
PartValues     = typ.List[typ.Tuple[str, str]]


def _format_part_values(vinfo: version.V2VersionInfo) -> PartValues:
    """Generate kwargs for template from minimal V2VersionInfo.

    The V2VersionInfo Tuple only has the minimal representation
    of a parsed version, not the values suitable for formatting.
    It may for example have month=9, but not the formatted
    representation '09' for '0M'.

    >>> vinfo = parse_version_info("v200709.1033-beta", raw_pattern="vYYYY0M.BUILD[-RELEASE]")
    >>> kwargs = dict(_format_part_values(vinfo))
    >>> (kwargs['YYYY'], kwargs['0M'], kwargs['BUILD'], kwargs['RELEASE'])
    ('2007', '09', '1033', 'beta')
    >>> (kwargs['YY'], kwargs['0Y'], kwargs['MM'], kwargs['PYTAG'])
    ('7', '07', '9', 'b')

    >>> vinfo = parse_version_info("200709.1033b1", raw_pattern="YYYY0M.BLD[PYTAGNUM]")
    >>> kwargs = dict(_format_part_values(vinfo))
    >>> (kwargs['YYYY'], kwargs['0M'], kwargs['BUILD'], kwargs['PYTAG'], kwargs['NUM'])
    ('2007', '09', '1033', 'b', '1')
    """
    vnfo_kwargs: TemplateKwargs = vinfo._asdict()
    kwargs     : typ.Dict[str, str] = {}

    for part, field in v2patterns.PATTERN_PART_FIELDS.items():
        field_val = vnfo_kwargs[field]
        if field_val is not None:
            format_fn = v2patterns.PART_FORMATS[part]
            kwargs[part] = format_fn(field_val)

    return sorted(kwargs.items(), key=lambda item: -len(item[0]))


def _clear_zero_segments(
    formatted_segs: typ.List[str], is_zero_segment: typ.List[bool]
) -> typ.List[str]:
    non_zero_segs = list(formatted_segs)

    has_val_to_right = False
    for idx, is_zero in reversed(list(enumerate(is_zero_segment))):
        is_optional = 0 < idx < len(formatted_segs) - 1
        if is_optional:
            if is_zero and not has_val_to_right:
                non_zero_segs[idx] = ""
            else:
                has_val_to_right = True

    return non_zero_segs


Segment = str
# mypy limitation wrt. cyclic definition
# SegmentTree = typ.List[typ.Union[Segment, "SegmentTree"]]
SegmentTree = typ.Any


def _parse_segment_tree(raw_pattern: str) -> SegmentTree:
    """Generate segment tree from pattern string.

    >>> tree = _parse_segment_tree("aa[bb[cc]]")
    >>> assert tree == ["aa", ["bb", ["cc"]]]
    >>> tree = _parse_segment_tree("aa[bb[cc]dd[ee]ff]gg")
    >>> assert tree == ["aa", ["bb", ["cc"], "dd", ["ee"], "ff"], "gg"]
    """

    internal_root: SegmentTree = []
    branch_stack : typ.List[SegmentTree] = [internal_root]
    segment_start_index = -1

    raw_pattern = "[" + raw_pattern + "]"

    for i, char in enumerate(raw_pattern):
        is_escaped = i > 0 and raw_pattern[i - 1] == "\\"
        if char in "[]" and not is_escaped:
            start = segment_start_index + 1
            end   = i
            if start < end:
                branch_stack[-1].append(raw_pattern[start:end])

            if char == "[":
                new_branch: SegmentTree = []
                branch_stack[-1].append(new_branch)
                branch_stack.append(new_branch)
                segment_start_index = i
            elif char == "]":
                if len(branch_stack) == 1:
                    err = f"Unbalanced brace(s) in '{raw_pattern}'"
                    raise ValueError(err)

                branch_stack.pop()
                segment_start_index = i
            else:
                raise NotImplementedError("Unreachable")

    if len(branch_stack) > 1:
        err = f"Unclosed brace in '{raw_pattern}'"
        raise ValueError(err)

    return internal_root[0]


FormattedSegmentParts = typ.List[str]


class FormatedSeg(typ.NamedTuple):
    is_literal: bool
    is_zero   : bool
    result    : str


def _format_segment(seg: Segment, part_values: PartValues) -> FormatedSeg:
    zero_part_count = 0

    # find all parts, regardless of zero value
    used_parts: typ.List[typ.Tuple[str, str]] = []

    for part, part_value in part_values:
        if part in seg:
            used_parts.append((part, part_value))
            if version.is_zero_val(part, part_value):
                zero_part_count += 1

    result = seg
    # unescape braces
    result = result.replace(r"\[", r"[")
    result = result.replace(r"\]", r"]")

    for part, part_value in used_parts:
        result = result.replace(part, part_value)

    # If a segment has no parts at all, it is a literal string
    # (typically a prefix or sufix) and should be output as is.
    is_literal_seg = len(used_parts) == 0
    if is_literal_seg:
        return FormatedSeg(True, False, result)
    elif zero_part_count > 0 and zero_part_count == len(used_parts):
        # all zero, omit segment completely
        return FormatedSeg(False, True, result)
    else:
        return FormatedSeg(False, False, result)


def _format_segment_tree(
    seg_tree   : SegmentTree,
    part_values: PartValues,
) -> FormatedSeg:
    # print("??>>>", seg_tree)
    # NOTE (mb 2020-10-02): starting from the right, if there is any non-zero
    #   part, all further parts going left will be used. In other words, a part
    #   is only omitted, if all parts to the right of it were also omitted.
    result_parts: typ.List[str] = []
    is_zero = True
    for seg in seg_tree:
        if isinstance(seg, list):
            formatted_seg = _format_segment_tree(seg, part_values)
        else:
            formatted_seg = _format_segment(seg, part_values)

        if formatted_seg.is_literal:
            result_parts.append(formatted_seg.result)
        else:
            is_zero = is_zero and formatted_seg.is_zero
            result_parts.append(formatted_seg.result)

    # print("<<<<", is_zero, result_parts)
    result = "" if is_zero else "".join(result_parts)
    return FormatedSeg(False, is_zero, result)


def format_version(vinfo: version.V2VersionInfo, raw_pattern: str) -> str:
    """Generate version string.

    >>> import datetime as dt
    >>> vinfo = parse_version_info("v200712.0033-beta", raw_pattern="vYYYY0M.BUILD[-RELEASE]")
    >>> vinfo_a = vinfo._replace(**cal_info(date=dt.date(2007, 1, 1))._asdict())
    >>> vinfo_b = vinfo._replace(**cal_info(date=dt.date(2007, 12, 31))._asdict())

    >>> format_version(vinfo_a, raw_pattern="vYY.BLD[-PYTAGNUM]")
    'v7.33-b0'

    >>> format_version(vinfo_a, raw_pattern="YYYY0M.BUILD[PYTAG[NUM]]")
    '200701.0033b'
    >>> format_version(vinfo_a, raw_pattern="vYY.BLD[-PYTAGNUM]")
    'v7.33-b0'
    >>> format_version(vinfo_a, raw_pattern="v0Y.BLD[-RELEASE[NUM]]")
    'v07.33-beta'

    >>> format_version(vinfo_a, raw_pattern="vYYYY0M.BUILD[-RELEASE[NUM]]")
    'v200701.0033-beta'
    >>> format_version(vinfo_b, raw_pattern="vYYYY0M.BUILD[-RELEASE[NUM]]")
    'v200712.0033-beta'

    >>> format_version(vinfo_a, raw_pattern="vYYYYw0W.BUILD[-RELEASE[NUM]]")
    'v2007w01.0033-beta'
    >>> format_version(vinfo_a, raw_pattern="vYYYYwWW.BLD[-RELEASE[NUM]]")
    'v2007w1.33-beta'
    >>> format_version(vinfo_b, raw_pattern="vYYYYw0W.BUILD[-RELEASE[NUM]]")
    'v2007w53.0033-beta'

    >>> format_version(vinfo_a, raw_pattern="vYYYYd00J.BUILD[-RELEASE[NUM]]")
    'v2007d001.0033-beta'
    >>> format_version(vinfo_a, raw_pattern="vYYYYdJJJ.BUILD[-RELEASE[NUM]]")
    'v2007d1.0033-beta'
    >>> format_version(vinfo_b, raw_pattern="vYYYYd00J.BUILD[-RELEASE[NUM]]")
    'v2007d365.0033-beta'

    >>> format_version(vinfo_a, raw_pattern="vGGGGwVV.BLD[PYTAGNUM]")
    'v2007w1.33b0'
    >>> format_version(vinfo_a, raw_pattern="vGGGGw0V.BUILD[-RELEASE[NUM]]")
    'v2007w01.0033-beta'
    >>> format_version(vinfo_b, raw_pattern="vGGGGw0V.BUILD[-RELEASE[NUM]]")
    'v2008w01.0033-beta'

    >>> vinfo_c = vinfo_b._replace(major=1, minor=2, patch=34, tag='final')

    >>> format_version(vinfo_c, raw_pattern="vYYYYwWW.BUILD-RELEASE")
    'v2007w53.0033-final'
    >>> format_version(vinfo_c, raw_pattern="vYYYYwWW.BUILD[-RELEASE[NUM]]")
    'v2007w53.0033'

    >>> format_version(vinfo_c, raw_pattern="vMAJOR.MINOR.PATCH")
    'v1.2.34'

    >>> vinfo_d = vinfo_b._replace(major=1, minor=0, patch=0, tag='final')
    >>> format_version(vinfo_d, raw_pattern="vMAJOR.MINOR.PATCH-RELEASENUM")
    'v1.0.0-final0'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR.MINOR.PATCH-RELEASE[NUM]")
    'v1.0.0-final'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR.MINOR.PATCH-RELEASE")
    'v1.0.0-final'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR.MINOR.PATCH[-RELEASE[NUM]]")
    'v1.0.0'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR.MINOR[.PATCH[-RELEASE[NUM]]]")
    'v1.0'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH[-RELEASE[NUM]]]]")
    'v1'

    >>> vinfo_d = vinfo_b._replace(major=1, minor=0, patch=2, tag='rc', pytag='rc', num=0)
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH]]")
    'v1.0.2'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH[-RELEASE[NUM]]]]")
    'v1.0.2-rc'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH[PYTAGNUM]]]")
    'v1.0.2rc0'
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH]]")
    'v1.0.2'

    >>> vinfo_d = vinfo_b._replace(major=1, minor=0, patch=0, tag='rc', num=2)
    >>> format_version(vinfo_d, raw_pattern="vMAJOR[.MINOR[.PATCH[-RELEASE[NUM]]]]")
    'v1.0.0-rc2'

    >>> vinfo_d = vinfo_b._replace(major=1, minor=0, patch=0, tag='rc', num=2)
    >>> format_version(vinfo_d, raw_pattern='__version__ = "vMAJOR[.MINOR[.PATCH[-RELEASE[NUM]]]]"')
    '__version__ = "v1.0.0-rc2"'
    """
    part_values   = _format_part_values(vinfo)
    seg_tree      = _parse_segment_tree(raw_pattern)
    formatted_seg = _format_segment_tree(seg_tree, part_values)
    return formatted_seg.result


def _incr_numeric(
    vinfo      : version.V2VersionInfo,
    major      : bool,
    minor      : bool,
    patch      : bool,
    release    : typ.Optional[str],
    release_num: bool,
) -> version.V2VersionInfo:
    # prevent truncation of leading zeros
    if int(vinfo.bid) < 1000:
        vinfo = vinfo._replace(bid=str(int(vinfo.bid) + 1000))

    vinfo = vinfo._replace(bid=lexid.next_id(vinfo.bid))

    if major:
        vinfo = vinfo._replace(major=vinfo.major + 1, minor=0, patch=0)
    if minor:
        vinfo = vinfo._replace(minor=vinfo.minor + 1, patch=0)
    if patch:
        vinfo = vinfo._replace(patch=vinfo.patch + 1)
    if release_num:
        vinfo = vinfo._replace(num=vinfo.num + 1)
    if release:
        if release != vinfo.tag:
            vinfo = vinfo._replace(num=0)
        vinfo = vinfo._replace(tag=release)
    return vinfo


def is_valid_week_pattern(raw_pattern) -> bool:
    has_yy_part = any(part in raw_pattern for part in ["YYYY", "YY", "0Y"])
    has_ww_part = any(part in raw_pattern for part in ["WW"  , "0W", "UU", "0U"])
    has_gg_part = any(part in raw_pattern for part in ["GGGG", "GG", "0G"])
    has_vv_part = any(part in raw_pattern for part in ["VV"  , "0V"])
    if not ((has_yy_part or has_gg_part) and (has_ww_part or has_vv_part)):
        return True
    elif has_yy_part and has_vv_part:
        alt1 = raw_pattern.replace("V", "W")
        alt2 = raw_pattern.replace("Y", "G")
        logger.error(f"Invalid pattern: '{raw_pattern}'. Maybe try {alt1} or {alt2}")
        return False
    elif has_gg_part and has_ww_part:
        alt1 = raw_pattern.replace("W", "V").replace("U", "V")
        alt2 = raw_pattern.replace("G", "Y")
        logger.error(f"Invalid pattern: '{raw_pattern}'. Maybe try {alt1} or {alt2}")
        return False
    else:
        return True


def incr(
    old_version: str,
    raw_pattern: str = "vYYYY0M.BUILD[-RELEASE[NUM]]",
    *,
    release    : typ.Optional[str] = None,
    major      : bool = False,
    minor      : bool = False,
    patch      : bool = False,
    release_num: bool = False,
    pin_date   : bool = False,
    date       : typ.Optional[dt.date] = None,
) -> typ.Optional[str]:
    """Increment version string.

    'old_version' is assumed to be a string that matches 'raw_pattern'
    """
    if not is_valid_week_pattern(raw_pattern):
        return None

    try:
        old_vinfo = parse_version_info(old_version, raw_pattern)
    except version.PatternError as ex:
        logger.error(str(ex))
        return None

    cur_cinfo = _ver_to_cal_info(old_vinfo) if pin_date else cal_info(date)

    if _is_cal_gt(old_vinfo, cur_cinfo):
        logger.warning(f"Old version appears to be from the future '{old_version}'")
        cur_vinfo = old_vinfo
    else:
        cur_vinfo = old_vinfo._replace(**cur_cinfo._asdict())

    cur_vinfo = _incr_numeric(
        cur_vinfo,
        major=major,
        minor=minor,
        patch=patch,
        release=release,
        release_num=release_num,
    )

    # TODO (mb 2020-09-20): New Rollover Behaviour:
    #   Reset major, minor, patch to zero if any part to the left of it is incremented

    new_version = format_version(cur_vinfo, raw_pattern)
    if new_version == old_version:
        logger.error("Invalid arguments or pattern, version did not change.")
        return None
    else:
        return new_version