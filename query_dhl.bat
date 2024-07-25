@echo off

set api-key="put key here"
set work_location="put folder location here"


set start_pwd=%cd%
cd %work_location%

python %work_location%\main.py %api-key%

cd %start_pwd%
pause