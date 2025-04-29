FROM python:3.9-slim

COPY entrypoint.sh /entrypoint.sh
COPY doctide.py /doctide.py
COPY utils/code_diff_lib.py /code_diff_lib.py
COPY requirements_doctide.txt /requirements_doctide.txt

ENTRYPOINT ["/entrypoint.sh"]