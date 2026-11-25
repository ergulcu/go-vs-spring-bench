FROM golang:1.27-alpine AS build
WORKDIR /src
# Bağımlılıklar ayrı katmanda: yalnızca go.mod/go.sum değişince yeniden indirilir (Spring Dockerfile'ındaki dependency:go-offline ile aynı mantık)
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/api .

# scratch: en küçük olası çalışma imajı (statik binary, shell yok)
FROM scratch
COPY --from=build /out/api /api
EXPOSE 8080
ENTRYPOINT ["/api"]
