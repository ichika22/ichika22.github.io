#!/bin/bash
# usage: make.sh <body-file> <out-path(dir under site)> <title> <desc>
body=$1; path=$2; title=$3; desc=$4
mkdir -p ".${path}"
esc(){ printf '%s' "$1" | sed -e 's/[&|\]/\&/g'; }
sed -e "s|__TITLE__|$(esc "$title")|g" -e "s|__DESC__|$(esc "$desc")|g" -e "s|__PATH__|$path|g" _build/head.html > ".${path}index.html"
cat "$body" _build/foot.html >> ".${path}index.html"
echo "built ${path}"
