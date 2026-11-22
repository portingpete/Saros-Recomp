@echo off
setlocal
python -B "%~dp0windows\run_milestone.py" %* --profile native-upload-scatter
exit /b %errorlevel%
