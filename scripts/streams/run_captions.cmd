@echo off
rem Streams-Captions (scheduled task, every minute, IgnoreNew): Gemma captions for Step 0 keyframes via the eGPU vLLM.
cd /d D:\streams
if exist CAPTIONS_DONE exit /b 0
if exist STOP_CAPTIONS exit /b 0
set PYTHONIOENCODING=utf-8
"C:\Program Files\Python312\python.exe" D:\streams\captions.py >> D:\streams\captions.out 2>&1
