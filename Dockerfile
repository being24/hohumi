FROM python:3.12-slim

ARG BOT_NAME="hohumi"

# set environment variables
ENV TZ='Asia/Tokyo'

# uv environment variables
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT='/usr/local/'
ENV UV_SYSTEM_PYTHON=1


WORKDIR /opt/${BOT_NAME}/
COPY ./ ./

RUN apt update && \
    apt upgrade -y && \
    apt install -y git build-essential nano curl tzdata

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# install dependencies
RUN uv sync --frozen --no-dev --no-cache

# add non-root user
RUN adduser --disabled-password --gecos "" ${BOT_NAME}
RUN chown -R ${BOT_NAME}:${BOT_NAME} /opt/${BOT_NAME}/

# switch to non-root user
USER ${BOT_NAME}

CMD ["python3","main.py"]