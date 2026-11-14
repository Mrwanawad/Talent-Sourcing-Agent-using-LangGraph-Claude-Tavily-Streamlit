#!/usr/bin/env bash
# raw.webm + marks.json -> docs/demo.gif. The ~2 min sourcing wait is sped up to ~5 s.
set -euo pipefail
cd "$(dirname "$0")"
read -r S R E < <(python -c "import json; m=json.load(open('marks.json')); print(m['sourcing_start'], m['review'], m['end'])")
SRC_SPEED=$(python -c "print(($R-$S)/5)")

CUT="[0:v]trim=0:$S,setpts=(PTS-STARTPTS)/1.3[a];\
[0:v]trim=$S:$R,setpts=(PTS-STARTPTS)/$SRC_SPEED[b];\
[0:v]trim=$R:$E,setpts=(PTS-STARTPTS)/1.25[c];\
[a][b][c]concat=n=3:v=1,fps=8,scale=900:-1:flags=lanczos"

ffmpeg -y -v error -i raw.webm -filter_complex "$CUT,palettegen=max_colors=64:stats_mode=diff" palette.png
ffmpeg -y -v error -i raw.webm -i palette.png -filter_complex "$CUT[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" ../demo.gif
rm -f palette.png
ls -la ../demo.gif
