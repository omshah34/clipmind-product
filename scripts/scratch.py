import subprocess

def test_ff(vf_str):
    print(f"Testing: {vf_str}")
    res = subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'color=c=black:s=128x72',
        '-vf', vf_str, '-frames:v', '1', '-f', 'null', '-'
    ], capture_output=True, text=True)
    out = [line for line in res.stderr.splitlines() if "Error" in line or "Unable to" in line]
    print("\n".join(out))
    print("-" * 40)

# The most robust way in FFmpeg filters for Windows paths:
# Pass `filename=C\:/test...`
test_ff(r"subtitles=filename=C\:/test/path.srt")

# Double escape:
test_ff(r"subtitles=C\\:/test/path.srt")

# Triple escape?
test_ff(r"subtitles=C\\\:/test/path.srt")

# Quoted
test_ff("subtitles='C:/test/path.srt'")
test_ff(r"subtitles='C\:/test/path.srt'")
