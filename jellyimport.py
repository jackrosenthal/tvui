import dataclasses
import hashlib
import re
from pathlib import Path
import shutil
import subprocess
from typing import Optional

import click
import prompt_toolkit.shortcuts as pt
from prompt_toolkit.completion import WordCompleter


_EPISODE_RE = re.compile(r"S(\d\d)E\d\d")
_YEAR_RE = re.compile(r"(?:19\d\d|20[012]\d)")


@dataclasses.dataclass
class Media:
    path: Path
    srt_path: Optional[Path] = None
    collection: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    series: Optional[str] = None
    season: Optional[str] = None
    episode: Optional[str] = None
    has_embedded_subtitles: bool = False

    @property
    def dest_path(self):
        if self.collection == "Shows":
            return (
                Path("Shows") / f"{self.series} ({self.year})" /
                f"Season {self.season}" /
                f"Episode {self.episode}{self.path.suffix}"
            )
        if self.collection == "Movies":
            return (
                Path("Movies") / f"{self.title} ({self.year})"
                / f"{self.title}{self.path.suffix}"
            )
        return None

    @property
    def srt_dest_path(self):
        if not self.srt_path:
            return None
        dest_path = self.dest_path
        if not dest_path:
            return None
        return self.dest_path.with_suffix(".en.srt")

    def populate_from_file_name(self):
        episode_match = _EPISODE_RE.search(self.path.name)
        if episode_match:
            self.collection = "Shows"
            self.season = episode_match.group(1)
            self.episode = episode_match.group(0)
        else:
            self.collection = "Movies"
        file_parts = re.split(r"[. \[\]]", self.path.stem)
        title_parts = []
        for part in file_parts:
            year_match = _YEAR_RE.search(part)
            if year_match:
                self.year = int(year_match.group(0))
                break
            if _EPISODE_RE.search(part):
                break
            if len(part) == len(part.encode()):
                # It's ASCII.
                title_parts.append(part)
        if self.collection == "Shows":
            self.series = " ".join(title_parts)
        else:
            self.title = " ".join(title_parts)

    def check_has_embedded_subtitles(self):
        if self.path.suffix != ".mkv":
            return
        result = subprocess.run(
            ["ffmpeg", "-i", self.path, "-map", "0:s:0", "-f", "srt", "-o", "/dev/null", "-y"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not result.returncode:
            self.has_embedded_subtitles = True

    def find_srt_candidates(self):
        def _yield_candidates():
            yield self.path.with_suffix(".srt")
            for dname in ("subs", "Subs", "Subtitles", "subtitles", "srt"):
                subs_dir = self.path.parent / dname
                if subs_dir.is_dir():
                    yield from subs_dir.glob("*.srt")
                    episode_subs_dir = subs_dir / self.path.stem
                    if episode_subs_dir.is_dir():
                        yield from episode_subs_dir.glob("*.srt")

        for x in _yield_candidates():
            if not x.is_file():
                continue
            yield x

    def copy_to_library(self, library_path):
        dest = library_path / self.dest_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, dest)
        if self.srt_path:
            shutil.copyfile(self.srt_path, library_path / self.srt_dest_path)


_MB = 1024 * 1024


def _fast_hash_file(path):
    size = path.stat().st_size
    hasher = hashlib.sha256()
    if size < 2 * _MB:
        hasher.update(path.read_bytes())
    else:
        with open(path, "rb") as f:
            hasher.update(f.read(_MB))
            f.seek(size - _MB)
            hasher.update(f.read(_MB))
    return hasher.hexdigest()


def _hash_dir(path, label, suffixes=(".mkv", ".mp4")):
    result = {}
    files = []
    with pt.ProgressBar(title=f"Enumerating {label}...") as pb:
        for fpath in pb(path.glob("**/*")):
            if fpath.suffix not in suffixes:
                continue
            if fpath.name.startswith("."):
                continue
            if not fpath.is_file():
                continue
            if fpath.stat().st_size < 2 * _MB:
                continue
            files.append(fpath)
    with pt.ProgressBar(title=f"Hashing {label}...") as pb:
        for fpath in pb(files):
            result[_fast_hash_file(fpath)] = fpath
    return result


def _get_medias(import_hashes):
    medias = []
    with pt.ProgressBar(title="Populating initial metadata...") as pb:
        for path in pb(import_hashes.values()):
            media = Media(path)
            media.populate_from_file_name()
            medias.append(media)
    with pt.ProgressBar(title="Checking for embedded subtitles...") as pb:
        for media in pb(medias):
            media.check_has_embedded_subtitles()
    medias.sort(key=lambda x: x.dest_path)
    return medias


@click.command()
@click.option("--library", type=Path, default="/home/tvui/Library")
@click.argument("import_dir", type=Path, required=True)
def main(library, import_dir):
    import_hashes = _hash_dir(import_dir, "files to import")
    if not import_hashes:
        click.echo("No files to import.")
        return 0
    library_hashes = _hash_dir(library, "library")
    for dup in set(library_hashes) & set(import_hashes):
        click.echo(
            f"Skip {import_hashes[dup]}, as it's already in the library at "
            f"{library_hashes[dup]}."
        )
        del import_hashes[dup]
    if not import_hashes:
        click.echo("No files to import.")
        return 0
    click.echo(f"{len(import_hashes)} files to import.")
    medias = _get_medias(import_hashes)
    medias_to_import = []
    for media in medias:
        if not pt.confirm(f"Import {media.path}?"):
            continue
        media.collection = pt.prompt(
            "Media collection: ",
            default=media.collection or "Movies",
        )
        if media.collection == "Movies":
            media.title = pt.prompt("Title: ", default=media.title or "")
        else:
            media.series = pt.prompt("Series: ", default=media.series or "")
            media.season = pt.prompt("Season: ", default=media.season or "01")
            media.episode = pt.prompt("Episode: ", default=media.episode or "S01E01")
        media.year = int(pt.prompt("Year: ", default=str(media.year or "")))
        if not media.has_embedded_subtitles:
            candidates = [str(x) for x in media.find_srt_candidates()]
            completer = WordCompleter(candidates)
            srt_file = pt.prompt(
                "SRT File:",
                default=candidates[0] if candidates else "",
                completer=completer
            )
            if srt_file:
                media.srt_path = Path(srt_file)
        medias_to_import.append(media)

    with pt.ProgressBar("Copying media into library...") as pb:
        for media in pb(medias_to_import):
            media.copy_to_library(library)


if __name__ == '__main__':
    main()
