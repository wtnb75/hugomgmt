# hugo manager

## import from wordpress db

- convert wp posts to markdown files
- convert wp comments to isso db
- generate redirect settings for nginx

## manage hugo settings

- generate single patch (diff from theme)
- apply patch
- convert/reformat yaml \<-> toml

## manage isso comments

- list comments
- send mail recent comments

## manage static site

- generate .gz for nginx's `gzip_static on;`
- generate .br for nginx-mod-brotli's `brotli_static on;`
- optimize images
- convert/reformat rdf1.0 \<-> rss2.0 \<-> atom

## manage open-webui chat

- convert chat to hugo's markdown

# tutorial (convert wordpress to hugo+isso)

- (build hugomgmt package)
    - `python -m build -w`
- dump your wordpress database
    - `mysqldump ... > data/sql/wordpress.sql`
- rsync your wordpress uploads dir
    - `rsync -av wp_server:/path/to/wordpress/wp-content/uploads/ data/uploads/`
- boot local db and hugomgmt shell
    - `docker compose up -d`
- `docker compose exec shell sh`
    - hugo new site
        - `apk add hugo`
        - `hugomgmt wp-init-hugo --output /hugo`
        - `hugomgmt isso-initdb`
    - apply theme
        - `apk add git`
        - `git clone --depth=1 https://github.com/Junyi-99/hugo-theme-anubis2.git /hugo/theme/your-theme`
            - ... or other favorite theme
    - convert contents
        - `mkdir /hugo/content`
        - `hugomgmt wp-convpost-all --copy-resource /hugo/content`
        - `hugomgmt wp-convcomment-all`
    - view hugo site
        - `cd /hugo && hugo serve`

# related links

- wordpress to hugo converters
    - https://gohugo.io/tools/migrations/#wordpress
- how to import dumped xml of wordpress/disqus to isso
    - https://isso-comments.de/docs/guides/quickstart/#migration
- static website compressor
    - https://github.com/rhpvorderman/gzip_static
