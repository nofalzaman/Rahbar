FROM nginxinc/nginx-unprivileged:1.28-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html

USER 101

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]