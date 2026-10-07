# Surah Audio Builder

A desktop app that builds a combined audio file for each surah of the Quran: **the sheikh recites a verse, then the spoken interpretation (tafsir) of that verse plays, then the next verse, and so on.**

It pairs the two audio folders automatically, finds where every verse starts and ends in both recordings, cuts them, and joins them. When it is not sure about a verse, it does not guess silently. It shows both tracks as waveforms so you can fix the cut points by eye and ear.

---

## What the output sounds like

```
[ surah number + surah name (from the interpretation audio) ]
[ verse 1 recited ]  [pause]  [verse 1 interpretation]  [pause]
[ verse 2 recited ]  [pause]  [verse 2 interpretation]  [pause]
...
```

- The spoken intro of the interpretation (the surah number and name) always comes first.
- In the recitation, the *isti'adha* (أعوذ بالله من الشيطان الرجيم) and the *basmala* (بسم الله الرحمن الرحيم) are **not** treated as a verse. They stay attached to verse 1. (In Al-Fatiha, the basmala is verse 1 itself.)
- Default pauses: 0.4 s after a recitation, 0.9 s after an interpretation.
- Output: MP3, 64 kbps, 24 kHz mono.

---

## How it works

1. **Pairing.** Files are matched by surah number (see *File naming* below).
2. **Transcription.** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribes both recordings with word-level timestamps. Results are cached on disk, so re-runs are fast.
3. **Finding the verses, in two passes.**
   - *Pass 1, text match (no AI):* the transcript is aligned against your reference `.docx` (the verse text for the recitation, the explanation text for the interpretation). This gives a first guess of where each verse starts.
   - *Pass 2, Gemini:* Gemini receives the numbered transcript, in windows of 20 verses, together with the guess. It returns the final start of each verse. It is told the isti'adha and basmala are not verses, that the interpretation opens with the surah number and name, and that no explanation words may be left out or pushed into the next verse.
4. **Independent check.** Each verse is scored by comparing its first and last words with the reference text. A low start score means a wrong start. A low end score means words were left out or pushed into the next verse. Verses where Gemini moved the start far from the text-match guess are flagged too.
5. **Cutting.** Whisper's word times are only accurate to about a quarter of a second, so they are used as a *hint*. Each boundary between two verses is searched for in the audio itself: the app finds the real pause near that point (using the recording's own noise level) and cuts inside it, leaving a short natural tail and lead-in. Every boundary is decided on its own, so one wrong timestamp cannot shift the verses after it. If no pause exists and the quietest point is still loud, the verse is flagged for Review. Everything is saved to a `.verses.json` file with start and end (in seconds) for every verse in both tracks.
6. **Combining.** A surah with no flagged verses is built automatically. A surah with flagged verses goes to the **Review** tab first.

---

## Requirements

- **Python 3.10+** (tested on 3.14)
- **ffmpeg** on your PATH
  - Windows: `winget install Gyan.FFmpeg`
- A **Gemini API key** (optional but recommended; without it only the text-match pass runs)
- A GPU is not required, but Whisper `large-v3` is much faster with one

## Installation

```bash
pip install -r requirements.txt
python app.py
```

`requirements.txt` installs: `flet`, `flet-desktop`, `faster-whisper`, `google-genai`, `pydub`, `numpy`, `Pillow`, `python-docx` (and `audioop-lts` on Python 3.13+).

The first time you pick a Whisper model, it is downloaded automatically.

---

## File naming

Pairing relies on the file names.

| Folder | Example name | What is read from it |
|---|---|---|
| Interpretation audio | `Egyptian_100 سورة العاديات_Tafseer_MM.wav` | `Egyptian` = language, `100` = surah number, `سورة العاديات` = surah name |
| Recitation audio | `100 - الشيخ محمود على البنا ｜ سورة العاديات ｜ تسجيلات الإذاعة المصرية.mp3` | the leading number (`100`) |
| Reference text (`.docx`) | `100 سورة العاديات.docx` or `Egyptian_100 سورة العاديات_Tafseer.docx` | the number (and the language, if it has a prefix) |

- Audio can be `.mp3 .m4a .wav .flac .ogg .opus .aac .webm .mp4 .wma`.
- Subfolders are scanned.
- If several languages share one reference folder, give the reference files the language prefix. Without it, only the surah number is used to match.
- If several recitations exist for one surah, the first one is used and a note is shown.
- Unrecognised files are listed in amber on the Build tab.

### Reference `.docx` format

Each verse is one block:

- The **verse text is in red**, for example `قال تعالى ﵥ… ١ﵤ`. The app keeps only the text between the ornamental brackets and ignores the verse number, the surah label and the "الآية N" label.
- The **explanation is in normal (non-red) text** after it.
- The number of blocks must match the verse count of the surah. If the file has extra stray red quotations, the smallest blocks are merged into the previous one.

**Several verses explained together.** If the book explains consecutive verses in one block (heading like `من الآية ٨ الى الآية ٩`), the app treats them as **one unit**: both verses are recited one after the other, then the single interpretation plays. In the Review tab such a unit is shown as `8-9`. The verse numbers are read from the red text, and the units must add up exactly to the surah's verse count; otherwise the app falls back to "one block per verse".

If a surah has no reference text, the app still works through Gemini alone, but **only for surahs up to 80 verses**.

---

## Using the app

### Tab 1 · Build

1. Choose the four folders: interpretation audio, recitation audio, reference text, and where to save finished files.
2. Paste your Gemini API key. Pick the Gemini model and the Whisper model.
3. Press **Scan & pair**. The list shows every pair found, with a note when a reference text is missing.
4. Choose **From surah / To surah** (the dropdown shows the surah names) and tick the language(s).
5. Press **Build**.

Tick **Overwrite finished files** to rebuild a surah that already has a finished file. By default those are skipped.

Settings are remembered between runs.

### Tab 2 · Review problems

Surahs with at least one flagged verse appear here, marked with a warning sign.

- The left list shows every verse (⚠ = flagged, ✓ = fine).
- Two stacked waveforms show the **recitation** and the **interpretation** around the current verse, with neighbouring verses in grey.
- **Click on the wave** to move the green START line or the red END line (choose which with the radio buttons), or use the ± nudge buttons for fine tuning.
- **Play buttons:** the whole verse, around the start, or around the end. ⏹ stops playback.
- **Heard / Expected** text is shown under each wave, so you can see what was recognised and what the book says.
- **✓ This verse is fine → next problem** clears the flag and jumps to the next flagged verse.
- **Save** keeps your edits. **Save & build audio** builds the final MP3.

---

## Output files

Inside the folder you chose for finished files:

```
Egyptian_100 سورة العاديات_Combined.mp3     <- the finished audio
_work/
  100_Egyptian.verses.json                    <- start/end of every verse, both tracks
  cache/                                      <- Whisper transcripts and waveform data
```

The `.verses.json` file contains, for each verse and each track: start and end in seconds, the text-match score, the reason for any flag, and the "heard" and "expected" text.

Do not delete `_work` if you want fast re-runs and to keep your Review edits.

---

## Settings you can change (`core.py`, class `Settings`)

| Setting | Default | Meaning |
|---|---|---|
| `gap_after_rec_ms` | 400 | pause after each recitation |
| `gap_after_taf_ms` | 900 | pause after each interpretation |
| `bitrate` | `64k` | MP3 bitrate |
| `window` | 20 | verses sent to Gemini per request |
| `disagree_words` | 4 | flag a verse if Gemini moved its start by more than this many words |
| `min_score` | 0.40 | flag a verse if its start/end text match is below this |
| `snap_ms` | 400 | how far (ms) a cut may move away from Whisper's word time to reach a real pause |
| `timeout_s` | 150 | give up on one Gemini request after this many seconds |

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| Red box "Audio must have either src or src_base64" | Fixed in the current version. Make sure both `app.py` and `core.py` are the latest. |
| "no reference text for surah N" | There is no `.docx` for that number in the reference folder, or its name does not start with the number. |
| The log stops at "marking the … verses…" | The app is waiting for Gemini. The log now shows each attempt and how long it took. Try a faster Gemini model if it is slow. |
| Voices sound sped up or like gibberish | An audio format mismatch (for example a stereo `.wav` joined with a mono mp3). The current version forces everything to 24 kHz mono. Rebuild with **Overwrite** ticked. Do not just press "Save & build" in Review, because that reuses old cut points. |
| The surah number and name are missing at the start | Verse 1 of the interpretation was placed at 0:00. The current version never lets it start before the spoken surah name, and flags verse 1 if the name cannot be found. |
| Many flagged verses | Use a larger Whisper model (`large-v3` or `large-v3-turbo`). `small` is much less accurate on Quranic recitation. |
| "Whisper heard too few words" | The audio is silent, the wrong file was paired, or the language is wrong. |
| Play buttons do nothing | Wait for "Loading waveforms…" to finish, then try again. |

## Limits

- Memory: audio is loaded as 24 kHz mono. The longest surahs (such as Al-Baqarah) can use several hundred MB, so build them on their own.
- Without a reference text, only surahs of up to 80 verses are supported.
- The Gemini API is billed by your Google account. The app shows the number of calls and tokens used when a batch finishes.
- Quran verse positions are decided by speech recognition plus AI. Always listen to a sample of the results, and use the Review tab for anything doubtful.

## Project files

```
app.py            the Flet user interface (Build tab + Review tab)
core.py           everything else: pairing, Whisper, text matching, Gemini, cutting, mixing
requirements.txt  Python packages
```
