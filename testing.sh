#!/bin/bash

op="flows"
start=$(date +%s)
cim-apps $op --apk /Users/iain/Documents/projects/machinelistening/otter/OtterAI\ Transcribe\ Voice\ Notes_3.91.0-5028_APKPure.apk --outdir /Users/iain/Desktop/ --profile
end=$(date +%s)
timestamp=$((end - start))
echo "$op extraction completed in $timestamp seconds."