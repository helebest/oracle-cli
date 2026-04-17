FROM alpine:3.21

RUN apk add --no-cache curl docker-cli tzdata coreutils

COPY keepalive.sh /keepalive.sh
RUN chmod +x /keepalive.sh

CMD ["/keepalive.sh"]
