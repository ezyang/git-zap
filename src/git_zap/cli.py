from __future__ import annotations

import asyncio
import configparser
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urljoin

import click

GLOBAL_STORE = Path.home() / ".local" / "share" / "git-zap"


def _resolve_url(base_url: str, relative_url: str) -> str:
    """Resolve a relative submodule URL against a base URL.

    Handles both standard URLs (https://...) and SSH-style URLs (git@host:path).
    """
    # If the URL is already absolute, return it as-is
    if "://" in relative_url or "@" in relative_url and ":" in relative_url:
        return relative_url

    # Handle SSH-style URLs like git@github.com:owner/repo.git
    if "@" in base_url and "://" not in base_url:
        # Parse git@host:path format
        user_host, path = base_url.split(":", 1)
        # Resolve the relative path
        resolved = str(PurePosixPath(path).parent / relative_url)
        # Normalize .. and . components
        parts = []
        for part in resolved.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        return f"{user_host}:{'/'.join(parts)}"

    # Handle standard URLs
    return urljoin(base_url, relative_url)


async def _run(args: Iterable[str], cwd: Path | None = None) -> None:
    cmd = list(args)
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(cwd) if cwd else None)
    ret = await proc.wait()
    if ret:
        raise subprocess.CalledProcessError(ret, cmd)


async def _check_output(args: Iterable[str], cwd: Path | None = None) -> str:
    cmd = list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return stdout.decode().strip()


def _parse_repo(repo: str) -> tuple[str, Path]:
    if "://" in repo:
        url = repo
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", repo)
        path = GLOBAL_STORE / "extern" / f"{safe}"
    else:
        owner, name = repo.split("/", 1)
        if name.endswith(".git"):
            name = name[:-4]
        url = f"git@github.com:{owner}/{name}.git"
        path = GLOBAL_STORE / "github" / owner / f"{name}"
    return url, path


async def _ensure_global_repo(url: str, repo_path: Path) -> None:
    if not repo_path.exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        await _run(["git", "clone", url, str(repo_path)])
    else:
        await _run(["git", "-C", str(repo_path), "fetch"])


async def _worktree_add(repo_path: Path, dest: Path, ref: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.is_dir() and not any(dest.iterdir()):
            dest.rmdir()
        else:
            return
    await _run(
        ["git", "-C", str(repo_path), "worktree", "add", "-f", "--detach", str(dest), ref]
    )


async def _get_submodules(dest: Path, parent_url: str) -> list[tuple[str, str, str]]:
    gitmodules = dest / ".gitmodules"
    if not gitmodules.exists():
        return []
    config = configparser.ConfigParser()
    config.read(gitmodules)
    subs: list[tuple[str, str, str]] = []
    for name in config.sections():
        path = config[name]["path"]
        raw_url = config[name]["url"]
        url = _resolve_url(parent_url, raw_url)
        try:
            commit = await _check_output(["git", "rev-parse", f"HEAD:{path}"], cwd=dest)
        except subprocess.CalledProcessError:
            print(f"Warning: skipping submodule '{path}' - not committed in tree")
            continue
        subs.append((path, url, commit))
    return subs


async def zap(repo: str, destination: Path, ref: str | None = None) -> None:
    url, repo_path = _parse_repo(repo)
    await _ensure_global_repo(url, repo_path)
    await _worktree_add(repo_path, destination, ref or "HEAD")
    subs = await _get_submodules(destination, url)
    await asyncio.gather(
        *(zap(sub_url, destination / path, commit) for path, sub_url, commit in subs)
    )


@click.command()
@click.argument("repo")
@click.argument("destination")
def main(repo: str, destination: str) -> None:
    """Zap REPO into DESTINATION using git worktrees."""
    dest = Path(destination).expanduser().resolve()
    asyncio.run(zap(repo, dest))
