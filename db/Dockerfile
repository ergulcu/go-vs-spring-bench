FROM postgres:18
# Şema ve tohum veri imajın içinde: bind mount gerekmez (runner konteynerinden de çalışır).
COPY init.sql /docker-entrypoint-initdb.d/init.sql
