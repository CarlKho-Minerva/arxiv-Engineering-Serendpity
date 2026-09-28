@echo off
rem Streams-Step0 (scheduled task, every minute, IgnoreNew): read each carlcrafters video once. No-op when done or stopped.
cd /d D:\streams
if exist STEP0_DONE exit /b 0
if exist STOP exit /b 0
set PYTHONIOENCODING=utf-8
"C:\Program Files\Python312\python.exe" D:\streams\step0.py >> D:\streams\step0.out 2>&1
