docker stop hohumi
docker rm hohumi
docker pull ghcr.io/being24/hohumi:latest
docker run -d -v hohumi-data:/opt/hohumi/data --env-file .env --restart=always --name=hohumi ghcr.io/being24/hohumi