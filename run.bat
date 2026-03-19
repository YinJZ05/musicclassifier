@echo off
title QQ音乐歌单处理器
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m musicclassifier
pause
