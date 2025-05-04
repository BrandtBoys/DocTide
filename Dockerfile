FROM python:3.9-slim

COPY entrypoint.sh /entrypoint.sh
COPY doctide.py /doctide.py
COPY utils/code_diff_utils.py /code_diff_utils.py
COPY requirements_doctide.txt /requirements_doctide.txt

ENTRYPOINT ["/entrypoint.sh"]