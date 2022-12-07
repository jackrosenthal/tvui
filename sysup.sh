#!/bin/bash
set -e

if [[ "${EUID}" -ne 0 ]]; then
    exec sudo "$0" "$@"
fi

pacman -Sy
pacman -S --needed archlinux-keyring
pacman -Su

echo
echo -n ":: Clear package cache [Y/n]? "
read response

case response in
    [Nn] ) ;;
    * )
        rm -rf /var/cache/pacman/pkg/*
esac
