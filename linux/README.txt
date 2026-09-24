TokenScope for Linux x86_64

Extract the archive and run:
  cd TokenScope-Linux-x86_64
  ./launch-tokenscope.sh

The launcher starts the dashboard, opens your default browser when possible, and
keeps collection in the foreground. Press Ctrl+C to stop TokenScope and its
active collection.

Edit your private machine settings at:
  ${XDG_CONFIG_HOME:-~/.config}/tokenscope/config.ini

The refresh cache is stored at:
  ${XDG_CACHE_HOME:-~/.cache}/tokenscope/web.json

By default, the dashboard is available to devices on your trusted LAN and has no
login or TLS. Do not expose it to the public Internet.
