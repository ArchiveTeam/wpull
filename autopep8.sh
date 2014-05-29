#/bin/sh
python3 -m autopep8 --in-place --verbose \
    --aggressive --aggressive --aggressive \
    --ignore E301,E309 \
    wpull/*.py \
    wpull/http/*.py \
    wpull/testing/*.py
