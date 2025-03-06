#!/bin/bash
# Copyright (C) 2023 by Henry Kroll III, www.thenerdshow.com
#
# With code contributions by Matthew Rensberry
#
# This is free software.  You may redistribute it under the terms
# of the Apache license and the GNU General Public License Version
# 2 or at your option any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#

# fifo queue to hold temporary audio file names
audio_fifo=$(mktemp); rm "$audio_fifo" ; mkfifo "$audio_fifo"

## create a trap to remove temp files on untimely exit
cleanup() {
    rm -f /tmp/tmp.txt "$audio_fifo"
}
trap cleanup 0

export YDOTOOL_SOCKET=/tmp/.ydotool_socket

# function to process audio files from queue
trans(){
    while read audio; do
        # Send audio file to whisper.cpp using curl
        curl_output=$(curl -s "http://127.0.0.1:7654/inference" \
                -H "Content-Type: multipart/form-data" \
                -F "file=@$audio" \
                -F "temperature=0.0" \
                -F "response-format=json")

        # Extract only the text field from JSON response and replace newlines with spaces
	    curl_output_text=$(echo "$curl_output" | grep -o '"text":"[^"]*' | sed 's/"text":"//' | tr -d '\n\r')

        # remove temporary audio file
        rm -f "$audio"
        echo "$curl_output_text"

        # Type text to terminal, in background
        # Thanks for watching! seems to occur frequently due to noise.
        if [[ ${#curl_output_text} > 5 ]] || [[ "$curl_output_text" != "Thanks for watching!" ]]; then
            ydotool type "$curl_output_text"
        fi &
    done < "$audio_fifo"
    #cleanup
    rm -f "$audio_fifo"
}

# record audio in background
while true; do
    # Make temporary files to hold audio
    tmp=$(mktemp)
    # Remove it on exit
    trap 'rm "$tmp" ; exit' INT

    # Listen to the mic.
    rec -c 2 -r 22050 -t mp3 "$tmp" silence 1 0.2 7% 1 0.5 6%

    # echo temporary audio file name to transcription queue
    echo "$tmp"
done > "$audio_fifo" & #The `&` lets recording run in the background.

# run audio transcription handler
trans
