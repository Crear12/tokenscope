TokenScope for Windows x64

Double-click launch-tokenscope.bat. It starts the dashboard, opens your browser,
and leaves this console open so collection progress is visible. Press Ctrl+C in
the console to stop TokenScope and its active collection.

Edit your private machine settings at:
%APPDATA%\TokenScope\config.ini

The refresh cache is stored under:
%LOCALAPPDATA%\TokenScope\output\web.json

By default, the dashboard is available to devices on your trusted LAN and has no
login or TLS. Do not expose it to the public Internet.
