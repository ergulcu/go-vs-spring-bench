# Orkestratör konteyneri: Python (yalnızca standart kütüphane) + Docker CLI + Compose eklentisi.
# Docker'a ana makinenin /var/run/docker.sock soketi üzerinden bağlanır; API konteynerlerini, veritabanını ve k6'yı kardeş konteyner olarak başlatır.
FROM docker:cli AS dockercli

FROM python:3.13-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
# buildx şart: yoksa Compose eski (BuildKit'siz) build'e düşer ve build süreleri referansla karşılaştırılamaz olur
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
ENTRYPOINT ["python", "scripts/run_all.py"]
