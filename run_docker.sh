#!/bin/bash

#script to show how to run the app_study.py script in a docker container
#change metadata to flows

docker run --rm \
  -v "$(pwd)/results:/results" \
  cim-apps \
  flows --apk app.apk --outdir /results