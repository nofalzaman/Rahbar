FROM alpine:3.24

RUN apk add --no-cache nginx && apk upgrade --no-cache

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html

USER 101

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
