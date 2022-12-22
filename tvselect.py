#!/usr/bin/env python3

import argparse
import dataclasses
import io
import pathlib
import shutil
import subprocess


HERE = pathlib.Path(__file__).parent


def rofi(items):
    stdin = io.StringIO()
    for item in items:
        print(item, file=stdin)

    try:
        result = subprocess.run(
            ["rofi", "-dmenu", "-format", "i"],
            input=stdin.getvalue(),
            stdout=subprocess.PIPE,
            check=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return MenuItemBack("Back", 1)

    result_i = int(result.stdout)
    return items[result_i]


@dataclasses.dataclass
class MenuItem:
    """Base class for all menu items."""

    text: str

    def probe(self):
        return True

    def select(self):
        return None

    def __str__(self):
        return self.text


@dataclasses.dataclass
class Back:
    pages: int


@dataclasses.dataclass
class MenuItemBack(MenuItem):
    pages: int

    def select(self):
        return Back(self.pages)


@dataclasses.dataclass
class MenuItemExec(MenuItem):
    """Run an application."""

    argv: list[str]

    def probe(self):
        return bool(shutil.which(self.argv[0]))

    def select(self):
        return subprocess.Popen(self.argv)


@dataclasses.dataclass
class MenuItemSub(MenuItem):
    """Sub-menu."""

    items: list[MenuItem]
    show_back: bool = True

    def probe(self):
        return any(x.probe() for x in self.items)

    def select(self):
        items = list(self.items)
        if self.show_back:
            items.append(MenuItemBack("Back", 1))
        return show_menu(items)


def show_menu(items):
    relevant = [x for x in items if x.probe()]
    if not relevant:
        return None
    while True:
        item = rofi(relevant)
        result = item.select()
        if isinstance(result, Back):
            if result.pages == 0:
                continue
            return Back(result.pages - 1)
        return result


GAMES = [
    MenuItemExec("GameHub", ["gamehub"]),
    MenuItemExec("Steam", ["steam", "-steamdeck", "-gamepadui"]),
    MenuItemExec("SuperTuxKart", ["supertuxkart"]),
    MenuItemExec("SuperTux", ["supertux2"]),
    MenuItemExec("Pingus", ["pingus"]),
    MenuItemExec("PySol", ["pysol"]),
    MenuItemExec("RetroArch", ["retroarch"]),
]

SYSTEM = [
    MenuItemExec("Volume Control", ["pavucontrol"]),
    MenuItemExec("Terminal", ["kitty"]),
    MenuItemExec("Update Packages", ["kitty", HERE / "sysup.sh"]),
    MenuItemExec("Kill Application", ["xkill"]),
    MenuItemExec("Power Off", ["poweroff"]),
    MenuItemExec("Reboot", ["reboot"]),
    MenuItemExec("Log Out", ["i3-msg", "exit"]),
    MenuItemExec("Restart Window Manager", ["i3-msg", "restart"]),
]

TOP = [
    MenuItemExec("Google Chrome", ["google-chrome-stable"]),
    MenuItemSub("Games", GAMES),
    MenuItemSub("System", SYSTEM),
]


def main():
    parser = argparse.ArgumentParser(description="TV Menu")
    parser.parse_args()

    show_menu(TOP)


if __name__ == "__main__":
    main()
