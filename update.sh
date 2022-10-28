docker stop hohumi
docker rm hohumi
# docker pull ghcr.io/being24/hohumi:latest
# docker run -d -v hohumi-data:/opt/hohumi/data -v hohumi-log:/opt/hohumi/log --env-file .env --restart=always --name=hohumi ghcr.io/being24/hohumi
docker compose up -d