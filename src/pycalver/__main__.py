#!/usr/bin/env python
# This file is part of the pycalver project
# https://gitlab.com/mbarkhau/pycalver
#
# Copyright (c) 2018 Manuel Barkhau (@mbarkhau) - MIT License
# SPDX-License-Identifier: MIT
"""
CLI module for pycalver.

Provided subcommands: show, init, incr, bump
"""

import io
import os
import sys
import click
import logging
import typing as typ

from . import vcs
from . import parse
from . import config
from . import version
from . import rewrite


_VERBOSE = 0


log = logging.getLogger("pycalver.cli")


def _init_logging(verbose: int = 0) -> None:
    if verbose >= 2:
        log_format = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-15s - %(message)s"
        log_level  = logging.DEBUG
    elif verbose == 1:
        log_format = "%(levelname)-7s - %(message)s"
        log_level  = logging.INFO
    else:
        log_format = "%(message)s"
        log_level  = logging.WARNING

    logging.basicConfig(level=log_level, format=log_format, datefmt="%Y-%m-%dT%H:%M:%S")
    log.debug("Logging initialized.")


@click.group()
@click.option('-v', '--verbose', count=True, help="Control log level. -vv for debug level.")
def cli(verbose: int = 0):
    """Automatically update PyCalVer version strings on python projects."""
    global _VERBOSE
    _VERBOSE = verbose


def _update_cfg_from_vcs(cfg: config.Config, fetch: bool) -> config.Config:
    try:
        _vcs = vcs.get_vcs()
        log.debug(f"vcs found: {_vcs.name}")
        if fetch:
            log.debug(f"fetching from remote")
            _vcs.fetch()

        version_tags = [tag for tag in _vcs.ls_tags() if parse.PYCALVER_RE.match(tag)]
        if version_tags:
            version_tags.sort(reverse=True)
            log.debug(f"found {len(version_tags)} tags: {version_tags[:2]}")
            latest_version_tag = version_tags[0]
            if latest_version_tag > cfg.current_version:
                log.info(f"Working dir version        : {cfg.current_version}")
                log.info(f"Latest version from {_vcs.name:>3} tag: {latest_version_tag}")
                cfg = cfg._replace(current_version=latest_version_tag)
        else:
            log.debug("no vcs tags found")
    except OSError:
        log.debug("No vcs found")

    return cfg


@cli.command()
@click.option('-v', '--verbose'         , count=True  , help="Control log level. -vv for debug level.")
@click.option('-f', "--fetch/--no-fetch", is_flag=True, default=True)
def show(verbose: int = 0, fetch: bool = True) -> None:
    """Show current version."""
    verbose = max(_VERBOSE, verbose)
    _init_logging(verbose=verbose)

    cfg: config.MaybeConfig = config.parse()
    if cfg is None:
        log.error("Could not parse configuration from setup.cfg")
        sys.exit(1)

    cfg = _update_cfg_from_vcs(cfg, fetch=fetch)

    print(f"Current Version: {cfg.current_version}")
    print(f"PEP440 Version : {cfg.pep440_version}")


@cli.command()
@click.argument("old_version")
@click.option('-v', '--verbose', count=True, help="Control log level. -vv for debug level.")
@click.option(
    "--release", default=None, metavar="<name>", help="Override release name of current_version"
)
def incr(old_version: str, verbose: int = 0, release: str = None) -> None:
    """Increment a version number for demo purposes."""
    verbose = max(_VERBOSE, verbose)
    _init_logging(verbose)

    if release and release not in parse.VALID_RELESE_VALUES:
        log.error(f"Invalid argument --release={release}")
        log.error(f"Valid arguments are: {', '.join(parse.VALID_RELESE_VALUES)}")
        sys.exit(1)

    new_version     = version.incr(old_version, release=release)
    new_version_nfo = parse.VersionInfo.parse(new_version)

    print("PyCalVer Version:", new_version)
    print("PEP440 Version:"  , new_version_nfo.pep440_version)


@cli.command()
@click.option('-v', '--verbose', count=True, help="Control log level. -vv for debug level.")
@click.option(
    "--dry", default=False, is_flag=True, help="Display diff of changes, don't rewrite files."
)
def init(verbose: int = 0, dry: bool = False) -> None:
    """Initialize [pycalver] configuration."""
    verbose = max(_VERBOSE, verbose)
    _init_logging(verbose)

    cfg   : config.MaybeConfig = config.parse()
    if cfg:
        log.error("Configuration already initialized in setup.cfg")
        sys.exit(1)

    cfg_lines = config.default_config_lines()

    if dry:
        print("Exiting because of '--dry'. Would have written to setup.cfg:")
        print("\n    " + "\n    ".join(cfg_lines))
        return

    if os.path.exists("setup.cfg"):
        cfg_content = "\n" + "\n".join(cfg_lines)
        with io.open("setup.cfg", mode="at", encoding="utf-8") as fh:
            fh.write(cfg_content)
        print("Updated setup.cfg")
    else:
        cfg_content = "\n".join(cfg_lines)
        with io.open("setup.cfg", mode="at", encoding="utf-8") as fh:
            fh.write(cfg_content)
        print("Created setup.cfg")


def _assert_not_dirty(vcs, filepaths: typ.Set[str], allow_dirty: bool):
    # TODO (mb 2018-11-11): This is mixing concerns. Move this up into __main__
    dirty_files = vcs.status()

    if dirty_files:
        log.warn(f"{vcs.name} working directory is not clean:")
        for dirty_file in dirty_files:
            log.warn("    " + dirty_file)

    if not allow_dirty and dirty_files:
        sys.exit(1)

    dirty_pattern_files = set(dirty_files) & filepaths
    if dirty_pattern_files:
        log.error("Not commiting when pattern files are dirty:")
        for dirty_file in dirty_pattern_files:
            log.warn("    " + dirty_file)
        sys.exit(1)


def _bump(cfg: config.Config, new_version: str, allow_dirty: bool = False) -> None:
    _vcs: typ.Optional[vcs.VCS]

    try:
        _vcs = vcs.get_vcs()
    except OSError:
        log.warn("Version Control System not found, aborting commit.")
        _vcs = None

    filepaths = set(cfg.file_patterns.keys())

    if _vcs:
        _assert_not_dirty(_vcs, filepaths, allow_dirty)

    rewrite.rewrite(new_version, cfg.file_patterns)

    if _vcs is None or not cfg.commit:
        return

    for filepath in filepaths:
        _vcs.add(filepath)

    _vcs.commit(f"bump version to {new_version}")

    if cfg.tag:
        _vcs.tag(new_version)
        _vcs.push(new_version)


@cli.command()
@click.option("-v", "--verbose"         , count=True  , help="Control log level. -vv for debug level.")
@click.option('-f', "--fetch/--no-fetch", is_flag=True, default=True)
@click.option(
    "--dry", default=False, is_flag=True, help="Display diff of changes, don't rewrite files."
)
@click.option(
    "--release", default=None, metavar="<name>", help="Override release name of current_version"
)
@click.option(
    "--allow-dirty",
    default=False,
    is_flag=True,
    help=(
        "Commit even when working directory is has uncomitted changes. "
        "(WARNING: The commit will still be aborted if there are uncomitted "
        "to files with version strings."
    ),
)
def bump(
    release    : typ.Optional[str] = None,
    verbose    : int  =     0,
    dry        : bool = False,
    allow_dirty: bool = False,
    fetch      : bool = True,
) -> None:
    """Increment the current version string and update project files."""
    verbose = max(_VERBOSE, verbose)
    _init_logging(verbose)

    if release and release not in parse.VALID_RELESE_VALUES:
        log.error(f"Invalid argument --release={release}")
        log.error(f"Valid arguments are: {', '.join(parse.VALID_RELESE_VALUES)}")
        sys.exit(1)

    cfg: config.MaybeConfig = config.parse()

    if cfg is None:
        log.error("Could not parse configuration from setup.cfg")
        sys.exit(1)

    cfg = _update_cfg_from_vcs(cfg, fetch=fetch)

    old_version = cfg.current_version
    new_version = version.incr(old_version, release=release)

    log.info(f"Old Version: {old_version}")
    log.info(f"New Version: {new_version}")

    if dry or verbose:
        print(rewrite.diff(new_version, cfg.file_patterns))

    if dry:
        return

    _bump(cfg, new_version, allow_dirty)
