FROM nginx:alpine AS build
ARG nginx_version=1.27.0
RUN apk add git make gcc musl-dev brotli-dev zlib-dev pcre-dev patch
ADD https://nginx.org/download/nginx-${nginx_version}.tar.gz /
RUN tar xfz /nginx-${nginx_version}.tar.gz
RUN git clone --depth=1 --single-branch https://github.com/google/ngx_brotli /ngx_brotli
RUN cd /ngx_brotli && git submodule update --init --recursive --recommend-shallow --depth 1
RUN cd nginx-${nginx_version} && ./configure --with-compat --add-dynamic-module=/ngx_brotli
RUN mkdir /modules
RUN cd nginx-${nginx_version} && make modules && cp objs/*.so /modules/
ADD nginx.conf.patch /etc/nginx
RUN cd /etc/nginx && patch -p0 < nginx.conf.patch

FROM nginx:alpine
COPY --from=build /modules/*.so /usr/lib/nginx/modules
COPY --from=build /etc/nginx/nginx.conf /etc/nginx/
