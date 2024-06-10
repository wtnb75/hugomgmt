#! /bin/sh

f=$(ls -1 /dist/*.whl | tail -n1)
[ -f "${f}" ] || f="hugomgmt"
pip install ${f}[ext]
exec sleep infinity
