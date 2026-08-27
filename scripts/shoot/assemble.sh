#!/usr/bin/env bash
# Assemble the 3:00 spine from the banked clips + the ElevenLabs voiceover.
# Every segment is rendered to identical params (1080p25 h264 + 48k stereo aac)
# and concatenated. Timings follow docs/voiceover-2026-08-26.md with the
# plan's own cuts applied: build 25s, agent 10s, the catch 40s.
set -euo pipefail
S="/c/Users/estev/AppData/Local/Temp/claude/c--Users-estev-Projects-STAR/5fbb557a-1256-4f3a-926d-856922c6f905/scratchpad"
D="$S/deliver"; VO="$S/vo/out"; SEG="$S/seg"; mkdir -p "$SEG"
REEL="$D/statics-reel.mp4"; BUILD="$D/shot-03-04-build-live-trim.mp4"; SWEEP="$D/shot-07-sweep-live.mp4"; CHECK="$D/shot-12b-check-inline.mp4"
SHOT1="/c/Users/estev/OneDrive/Pictures/Screenshots/Screenshot 2026-08-26 122407.png"
FONT="C\\:/Windows/Fonts/consola.ttf"
VENC="-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 25 -s 1920x1080"
AENC="-c:a aac -b:a 160k -ar 48000 -ac 2"

# seg NAME DURATION VIDEO_FILTERGRAPH_INPUTS... ; helper pieces below
silent() { echo "-f lavfi -i anullsrc=r=48000:cl=stereo"; }

# 0. title card — 4s, fade in/out, silent (title.png rendered from title.html by render_title.py)
ffmpeg -v error -y -loop 1 -framerate 25 -i "$S/title/title.png" $(silent) -filter_complex "[0:v]fade=t=in:st=0:d=0.6,fade=t=out:st=3.4:d=0.6,setsar=1,trim=duration=4[v]" -map "[v]" -map 1:a -t 4 $VENC $AENC "$SEG/00.mp4"

# 1. open — still image, 16s (was 20s; the 4s paid for the end card), vo-01 (8.4s) from 1.0s
ffmpeg -v error -y -loop 1 -framerate 25 -i "$SHOT1" -i "$VO/vo-01-open.mp3" \
  -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#1b1f1c,setsar=1,trim=duration=16[v];[1:a]adelay=1000|1000,apad=whole_dur=16[a]" \
  -map "[v]" -map "[a]" -t 16 $VENC $AENC "$SEG/01.mp4"

# 2. intake paste — reel 2.5..7.5, 5s, silent
ffmpeg -v error -y -ss 2.5 -t 5 -i "$REEL" $(silent) -filter_complex "[0:v]setsar=1[v]" -map "[v]" -map 1:a -t 5 $VENC $AENC "$SEG/02.mp4"

# 3+4. build — source 8s..146s (138s) ramped to 25s, elapsed counter burned, vo-03-04 from 0.5s
F=$(python -c "print(138/25)")
ffmpeg -v error -y -ss 8 -t 138 -i "$BUILD" -i "$VO/vo-03-04-build.mp3" \
  -filter_complex "[0:v]setpts=PTS/${F},fps=25,drawtext=fontfile='${FONT}':text='REAL TIME  %{eif\:floor(t*${F}/60)\:d}\:%{eif\:mod(floor(t*${F})\,60)\:d\:2}':fontcolor=#e9dcc0:fontsize=34:box=1:boxcolor=#1b1f1c@0.85:boxborderw=14:x=w-tw-48:y=48,setsar=1[v];[1:a]adelay=500|500,apad=whole_dur=25[a]" \
  -map "[v]" -map "[a]" -t 25 $VENC $AENC "$SEG/03.mp4"

# 5. receipt — reel 17.5..33.5, 16s (was 20s; the 4s paid for the title card), vo-05 from 1.0s
ffmpeg -v error -y -ss 17.5 -t 16 -i "$REEL" -i "$VO/vo-05-receipt.mp3" \
  -filter_complex "[0:v]setsar=1[v];[1:a]adelay=1000|1000,apad=whole_dur=16[a]" \
  -map "[v]" -map "[a]" -t 16 $VENC $AENC "$SEG/05.mp4"

# 6. draft paste — reel 35.5..40.5, 5s, silent
ffmpeg -v error -y -ss 35.5 -t 5 -i "$REEL" $(silent) -filter_complex "[0:v]setsar=1[v]" -map "[v]" -map 1:a -t 5 $VENC $AENC "$SEG/06.mp4"

# 7. sweep — source 8.6s..156.6s (148s) ramped to 22s, counter burned, vo-07 (19.8s) from 0.5s
F=$(python -c "print(148/22)")
ffmpeg -v error -y -ss 8.6 -t 148 -i "$SWEEP" -i "$VO/vo-07-sweep.mp3" \
  -filter_complex "[0:v]setpts=PTS/${F},fps=25,drawtext=fontfile='${FONT}':text='31 SCENES · ONE REQUEST   REAL TIME  %{eif\:floor(t*${F}/60)\:d}\:%{eif\:mod(floor(t*${F})\,60)\:d\:2}':fontcolor=#e9dcc0:fontsize=34:box=1:boxcolor=#1b1f1c@0.85:boxborderw=14:x=w-tw-48:y=48,setsar=1[v];[1:a]adelay=500|500,apad=whole_dur=22[a]" \
  -map "[v]" -map "[a]" -t 22 $VENC $AENC "$SEG/07.mp4"

# 8. numbers — reel 44.3..51.3, 7s, vo-08 (5.1s) from 0.3s
ffmpeg -v error -y -ss 44.3 -t 7 -i "$REEL" -i "$VO/vo-08-numbers.mp3" \
  -filter_complex "[0:v]setsar=1[v];[1:a]adelay=300|300,apad=whole_dur=7[a]" -map "[v]" -map "[a]" -t 7 $VENC $AENC "$SEG/08.mp4"

# 9. eleven + blisters — reel 52.3..62.3 (10s) + 10s hold, vo-09 from 0.8s
ffmpeg -v error -y -ss 52.3 -t 10 -i "$REEL" -i "$VO/vo-09-eleven-blisters.mp3" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=10,setsar=1[v];[1:a]adelay=800|800,apad=whole_dur=20[a]" \
  -map "[v]" -map "[a]" -t 20 $VENC $AENC "$SEG/09.mp4"

# 10. the catch — 36s: reel 62.3..72.3 (Casbah cluster, 10s) + 11s hold, then check 168..181 (inline marks, 13s) + 2s hold
#     vo-10a (20.6s) from 0.5s, vo-10b (8.5s) from 22.0s
ffmpeg -v error -y -ss 62.3 -t 10 -i "$REEL" -ss 168 -t 13 -i "$CHECK" -i "$VO/vo-10a-casbah.mp3" -i "$VO/vo-10b-writers-business.mp3" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=11,setsar=1[v0];[1:v]tpad=stop_mode=clone:stop_duration=2,setsar=1[v1];[v0][v1]concat=n=2:v=1:a=0[v];[2:a]adelay=500|500[a0];[3:a]adelay=22000|22000[a1];[a0][a1]amix=inputs=2:normalize=0,apad=whole_dur=36[a]" \
  -map "[v]" -map "[a]" -t 36 $VENC $AENC "$SEG/10.mp4"

# 11. agent door — two cards, 5s each (mcp-tools.png, mcp-defend.png via render_card.py), vo-11 from 0.5s
ffmpeg -v error -y -loop 1 -framerate 25 -t 5 -i "$S/title/mcp-tools.png" -loop 1 -framerate 25 -t 5 -i "$S/title/mcp-defend.png" -i "$VO/vo-11-agent.mp3" \
  -filter_complex "[0:v]fade=t=in:st=0:d=0.5,setsar=1[a0];[1:v]fade=t=out:st=4.5:d=0.5,setsar=1[a1];[a0][a1]concat=n=2:v=1:a=0[v];[2:a]adelay=500|500,apad=whole_dur=10[a]" \
  -map "[v]" -map "[a]" -t 10 $VENC $AENC "$SEG/11.mp4"

# 12. close — check 176..181 (5s) + 5s hold on the flagged page, vo-12 from 0.8s
ffmpeg -v error -y -ss 176 -t 5 -i "$CHECK" -i "$VO/vo-12-close.mp3" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=5,setsar=1[v];[1:a]adelay=800|800,apad=whole_dur=10[a]" \
  -map "[v]" -map "[a]" -t 10 $VENC $AENC "$SEG/12.mp4"

# 13. end card — 4s, fade in/out, silent (end.png from end.html via render_card.py end)
ffmpeg -v error -y -loop 1 -framerate 25 -i "$S/title/end.png" $(silent) -filter_complex "[0:v]fade=t=in:st=0:d=0.6,fade=t=out:st=3.4:d=0.6,setsar=1,trim=duration=4[v]" -map "[v]" -map 1:a -t 4 $VENC $AENC "$SEG/13.mp4"

# concat
: > "$SEG/list.txt"
cd "$SEG"; for n in 00 01 02 03 05 06 07 08 09 10 11 12 13; do echo "file '$n.mp4'" >> "$SEG/list.txt"; done
ffmpeg -v error -y -f concat -safe 0 -i "$SEG/list.txt" -c copy -movflags +faststart "$D/star-spine-3min.mp4"
ffprobe -v error -show_entries format=duration -show_entries stream=codec_type,width,height -of default=nw=1 "$D/star-spine-3min.mp4"
