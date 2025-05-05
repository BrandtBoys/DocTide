FROM python:3.9-slim

COPY entrypoint.sh /entrypoint.sh
COPY doctide.py /doctide.py
COPY utils /utils
COPY requirements_doctide.txt /requirements_doctide.txt

ENTRYPOINT ["/entrypoint.sh"]