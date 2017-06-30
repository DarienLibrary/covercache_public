FROM python:3.4

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get install -y freetds-dev
RUN apt-get install -y freetds-bin
RUN apt-get install -y libpq-dev
COPY requirements.txt /tmp/
RUN useradd celery
RUN pip3 install -r /tmp/requirements.txt

WORKDIR /covercache
