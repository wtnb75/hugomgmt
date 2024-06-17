#! /bin/sh

output=/hugo
theme=https://github.com/Junyi-99/hugo-theme-anubis2.git

set -exu
apk add hugo
hugomgmt wp-init-hugo --output ${output}
hugomgmt isso-initdb
apk add git
git clone --depth=1 ${theme} ${output}/themes/your-theme
mkdir -p ${output}/content
hugomgmt wp-convpost-all --copy-resource ${output}/content
hugomgmt wp-convcomment-all

#cd ${output} && hugo serve --bind 0.0.0.0

#cd ${output} && hugo --minify
#hugomgmt static-brotli ${output}/public

cd ${output} && hugo
