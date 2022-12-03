FROM python:3.11-alpine

WORKDIR /usr/src/app

RUN set -x \
    # requirements for backend \
    && apk add --no-cache wireguard-tools \
    # add non root user
    && addgroup -g 1000 -S abc \
    && adduser -u 1000 -S abc -G abc

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
