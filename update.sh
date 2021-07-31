docker stop hofumi
docker rm hofumi
docker pull ghcr.io/being24/hofumi:latest
docker run -d -v hofumi-data:/opt/hofumi/data --env-file .env --restart=always --name=hofumi ghcr.io/being24/hofumi