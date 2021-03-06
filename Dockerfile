FROM python:3.8-alpine

ARG BOT_NAME="hohumi"

WORKDIR /opt/

ENV LC_CTYPE='C.UTF-8'
ENV TZ='Asia/Tokyo'
ENV DEBIAN_FRONTEND=noninteractive

RUN set -x && \
    apk add --no-cache build-base nano git tzdata ncdu && \
    cp /usr/share/zoneinfo/Asia/Tokyo /etc/localtime && \
    python3 -m pip install -U setuptools && \
    git clone https://github.com/being24/${BOT_NAME}.git && \
    python3 -m pip install -r ./${BOT_NAME}/requirements.txt && \
    chmod 0700 ./${BOT_NAME}/*.sh && \
    chmod 0700 ./${BOT_NAME}/bot.py && \
    apk del build-base  && \
    rm -rf /var/cache/apk/*  && \
    echo "Hello, ${BOT_NAME} ready!"

CMD ["/opt/hohumi/bot.sh"]