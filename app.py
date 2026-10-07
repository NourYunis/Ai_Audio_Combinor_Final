"""app.py - Surah Audio Builder.   run:  python app.py"""
import base64
import io
import json
import threading
import time
from pathlib import Path

import flet as ft

import core

WW, HH = 1000, 110          # waveform size in pixels
BLANK = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="   # 1x1 png: an Image may never be empty


def main(page: ft.Page):
    page.title = "Surah Audio Builder"
    page.padding = 16
    store = page.client_storage
    saved = lambda k, d="": d if store.get(k) is None else store.get(k)

    # ============================================================ BUILD TAB =================== #
    fields = {}

    def folder_row(key, label):
        tf = ft.TextField(label=label, value=saved(key), expand=True, dense=True)
        fields[key] = tf
        picker = ft.FilePicker(on_result=lambda e: (setattr(tf, "value", e.path), tf.update()) if e.path else None)
        page.overlay.append(picker)
        return ft.Row([tf, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.get_directory_path())])

    rows = [folder_row("taf_dir", "Interpretation audio folder   (e.g. Egyptian_100 سورة العاديات_Tafseer_MM)"),
            folder_row("rec_dir", "Recitation audio folder   (e.g. 100 - الشيخ ... ｜ سورة العاديات ｜ ...)"),
            folder_row("ref_dir", "Interpretation TEXT folder   (e.g. Egyptian_100 سورة العاديات_Tafseer.docx)"),
            folder_row("final_dir", "Save finished files to")]
    api = ft.TextField(label="Gemini API key", password=True, can_reveal_password=True, dense=True,
                       value=saved("api"), expand=True)
    model = ft.TextField(label="Gemini model", value=saved("model", "gemini-3.1-pro-preview"), dense=True, width=260)
    whisper = ft.Dropdown(label="Whisper model", value=saved("whisper", "large-v3"), width=170, dense=True,
                          options=[ft.dropdown.Option(x) for x in ("large-v3", "large-v3-turbo", "medium", "small")])
    surah_opts = lambda: [ft.dropdown.Option(str(i), f"{i} - {core.SURAH_NAMES[i - 1]}") for i in range(1, 115)]
    s_from = ft.Dropdown(label="From surah", value="1", width=260, dense=True, options=surah_opts())
    s_to = ft.Dropdown(label="To surah", value="114", width=260, dense=True, options=surah_opts())
    overwrite = ft.Switch(label="Overwrite finished files")
    lang_row = ft.Row(wrap=True)
    pair_list = ft.ListView(height=170, spacing=1)
    state = {"jobs": []}

    log = ft.ListView(height=240, spacing=1, auto_scroll=True)
    bar, status = ft.ProgressBar(value=0), ft.Text("Idle")

    def add(msg):
        c = ft.Colors.RED_400 if "✗" in msg else ft.Colors.AMBER_400 if msg.lstrip().startswith("!") else \
            ft.Colors.GREEN_300 if "✓" in msg else None
        log.controls.append(ft.Text(msg, size=12, selectable=True, color=c, font_family="Consolas"))
        page.update()

    def scan(_=None):
        for k in ("taf_dir", "rec_dir"):
            if not Path(fields[k].value or "/nonexistent").is_dir():
                return add("✗ Choose the interpretation and recitation folders first.")
        ref = fields["ref_dir"].value
        jobs, problems = core.pair(fields["taf_dir"].value, fields["rec_dir"].value,
                                   ref if ref and Path(ref).is_dir() else None)
        state["jobs"] = jobs
        langs = sorted({j.lang for j in jobs})
        lang_row.controls = [ft.Checkbox(label=f"{l} ({sum(j.lang == l for j in jobs)})", data=l, value=True)
                             for l in langs]
        pair_list.controls = [ft.Text(f"✓ {j.number:>3}  {j.lang:<12} {j.name:<22} ↔ {j.rec.name[:46]}"
                                      + ("" if j.ref else "   (no text)"), size=12, font_family="Consolas")
                              for j in jobs] + \
                             [ft.Text("! " + p, size=12, color=ft.Colors.AMBER_400) for p in problems]
        status.value = f"{len(jobs)} pair(s) found, {len(problems)} problem(s)"
        page.update()

    run_btn = ft.FilledButton("Build", icon=ft.Icons.PLAY_ARROW)
    stop_btn = ft.OutlinedButton("Stop", icon=ft.Icons.STOP, disabled=True)
    stop_ev = threading.Event()

    def build(_):
        if not state["jobs"]:
            scan()
        if not fields["final_dir"].value:
            return add("✗ Choose where to save the finished files.")
        if not api.value.strip():
            add("! No Gemini key: only the text-match is used (no AI double check).")
        for k, tf in fields.items():
            store.set(k, tf.value or "")
        store.set("api", api.value)
        store.set("model", model.value)
        store.set("whisper", whisper.value)
        lo, hi = sorted((int(s_from.value), int(s_to.value)))
        chosen = tuple(c.data for c in lang_row.controls if c.value)
        cfg = core.Settings(final_dir=Path(fields["final_dir"].value), api_key=api.value.strip(),
                            model=model.value.strip(), whisper_model=whisper.value, overwrite=overwrite.value)
        jobs = [j for j in state["jobs"] if lo <= j.number <= hi and j.lang in chosen]
        stop_ev.clear()
        run_btn.disabled, stop_btn.disabled = True, False
        log.controls.clear()
        page.update()

        def work():
            res = core.run_batch(cfg, jobs, add, lambda d, t: (setattr(bar, "value", d / max(t, 1)), page.update()),
                                 stop_ev)
            bad = sum(r["status"] != "ok" for r in res)
            u = cfg.usage
            add(f"Done. {len(res)} processed, {bad} need review.  Gemini: {u['calls']} call(s), "
                f"{u['in']:,} in / {u['out']:,} out tokens.")
            status.value = f"{bad} job(s) need review -> Review tab" if bad else "Finished"
            run_btn.disabled, stop_btn.disabled = False, True
            refresh_jobs()
            page.update()
        threading.Thread(target=work, daemon=True).start()

    run_btn.on_click = build
    stop_btn.on_click = lambda _: (stop_ev.set(), add("⏹ stopping after the current step..."))

    build_tab = ft.Column([
        *rows, ft.Row([api, model, whisper]),
        ft.Row([ft.FilledTonalButton("Scan & pair", icon=ft.Icons.LINK, on_click=scan), s_from, s_to, overwrite]),
        lang_row, ft.Container(pair_list, border=ft.border.all(1, ft.Colors.GREY_700), padding=6),
        ft.Row([run_btn, stop_btn, status]), bar,
        ft.Container(log, border=ft.border.all(1, ft.Colors.GREY_700), padding=6)], scroll=ft.ScrollMode.AUTO)

    # ============================================================ REVIEW TAB ================== #
    R = {"data": None, "path": None, "v": 1, "pk": {}, "seg": {}, "win": {}, "mode": {"rec": "start", "taf": "start"}}
    job_dd = ft.Dropdown(label="Surah to review", width=420, dense=True)
    rmsg = ft.Text("", size=13)
    verse_list = ft.ListView(width=150, height=560, spacing=0)
    auds = {}                      # kind -> the Audio control currently playing (created on demand, never empty)

    def work_dir():
        return Path(fields["final_dir"].value or ".") / "_work"

    def refresh_jobs(_=None):
        items = []
        for p in sorted(work_dir().glob("*.verses.json")):
            try:
                d = json.loads(p.read_text("utf-8"))
                items.append((d["status"] != "ok", p, f"{'⚠' if d['status'] != 'ok' else '✓'} {p.name[:-12]}"))
            except Exception:
                pass
        items.sort(key=lambda x: (not x[0], x[1].name))
        job_dd.options = [ft.dropdown.Option(str(p), t) for _, p, t in items]
        page.update()

    def flagged(v):
        d = R["data"]
        return bool(d["rec"][v - 1]["flag"] or d["taf"][v - 1]["flag"])

    def vlabel(k):
        return R["data"]["rec"][k - 1].get("label", str(k))

    def fill_list():
        d = R["data"]
        verse_list.controls = [ft.ListTile(
            title=ft.Text(vlabel(k), size=13), dense=True, selected=(k == R["v"]),
            leading=ft.Icon(ft.Icons.WARNING_AMBER if flagged(k) else ft.Icons.CHECK, size=16,
                            color=ft.Colors.AMBER_400 if flagged(k) else ft.Colors.GREEN_400),
            on_click=lambda e, k=k: goto(k)) for k in range(1, d["verses"] + 1)]
        page.update()

    def goto(v):
        R["v"] = v
        fill_list()
        for p in panels.values():
            p["draw"]()

    def stop_audio(kind=None):
        for k in ([kind] if kind else list(auds)):
            a = auds.pop(k, None)
            if a is not None:
                try:
                    a.pause()
                except Exception:
                    pass
                if a in page.overlay:
                    page.overlay.remove(a)
        page.update()

    def play(kind, s, e):
        """Cut the part to play, hand it to Flet as base64 (no file paths, no seeking)."""
        seg = R["seg"].get(kind)
        if seg is None:
            rmsg.value = "Audio is still loading..."
            return page.update()
        s, e = max(s, 0), min(max(e, s + 0.3), len(seg) / 1000)
        buf = io.BytesIO()
        seg[int(s * 1000): int(e * 1000)].set_frame_rate(16000).export(buf, format="wav")
        for k in list(auds):                       # one sound at a time
            stop_audio(k)
        a = ft.Audio(src_base64=base64.b64encode(buf.getvalue()).decode(), autoplay=True)
        auds[kind] = a
        page.overlay.append(a)
        page.update()

    panels = {}

    def make_panel(kind, title):
        img = ft.Image(src_base64=BLANK, width=WW, height=HH, fit=ft.ImageFit.FILL)
        info, flag = ft.Text(size=13, weight=ft.FontWeight.W_500), ft.Text(size=12, color=ft.Colors.AMBER_400)
        heard, expected = ft.Text(size=12, selectable=True), ft.Text(size=12, selectable=True,
                                                                    color=ft.Colors.GREY_500)

        def ent():
            return R["data"][kind][R["v"] - 1]

        def draw():
            d = R["data"]
            if not d or kind not in R["pk"]:
                return
            e, total = ent(), d[kind + "_total"]
            t0 = max(0.0, e["start"] - 6)
            t1 = min(total, max(e["end"] + 6, t0 + 4))
            R["win"][kind] = (t0, t1)
            others = [(x["start"], x["end"]) for x in d[kind] if x["verse"] != R["v"] and x["end"] > t0
                      and x["start"] < t1]
            img.src_base64 = core.waveform_b64(R["pk"][kind], t0, t1, others, (e["start"], e["end"]), WW, HH)
            info.value = f"{title} - verse {vlabel(R['v'])}:   start {e['start']:.2f}s    end {e['end']:.2f}s    " \
                         f"(length {e['end'] - e['start']:.1f}s)"
            flag.value = ("⚠ " + e["flag"]) if e["flag"] else ""
            heard.value = "Heard:      " + e["heard"]
            expected.value = ("Expected:  " + e["expected"]) if e["expected"] else ""
            page.update()

        def set_time(which, t):
            e, total = ent(), R["data"][kind + "_total"]
            e[which] = round(min(max(t, 0), total), 3)
            if e["end"] <= e["start"] + 0.1:
                e["end" if which == "start" else "start"] = round(e[which] + (0.3 if which == "start" else -0.3), 3)
            draw()

        def click(ev):
            t0, t1 = R["win"][kind]
            set_time(R["mode"][kind], t0 + ev.local_x / WW * (t1 - t0))

        def nudges(which, label):
            return ft.Row([ft.Text(label, width=48)] + [
                ft.OutlinedButton(f"{d:+g}s", on_click=lambda _, d=d: set_time(which, ent()[which] + d))
                for d in (-1, -0.25, -0.05, 0.05, 0.25, 1)], spacing=4)

        mode = ft.RadioGroup(value="start", on_change=lambda e: R["mode"].__setitem__(kind, e.control.value),
                             content=ft.Row([ft.Text("Click on the wave to move:"),
                                             ft.Radio(value="start", label="START"),
                                             ft.Radio(value="end", label="END")]))
        buttons = ft.Row([
            ft.FilledTonalButton("▶ Verse", on_click=lambda _: play(kind, ent()["start"], ent()["end"])),
            ft.OutlinedButton("▶ Around start", on_click=lambda _: play(kind, ent()["start"] - 1, ent()["start"] + 2)),
            ft.OutlinedButton("▶ Around end", on_click=lambda _: play(kind, ent()["end"] - 2, ent()["end"] + 1)),
            ft.OutlinedButton("⏹", on_click=lambda _: stop_audio(kind))])
        card = ft.Container(ft.Column([
            info, flag, ft.GestureDetector(content=img, on_tap_down=click), mode, buttons,
            nudges("start", "Start"), nudges("end", "End"), heard, expected], spacing=4),
            padding=10, border=ft.border.all(1, ft.Colors.GREY_700), border_radius=8)
        panels[kind] = {"card": card, "draw": draw}
        return card

    rec_card = make_panel("rec", "RECITATION")
    taf_card = make_panel("taf", "INTERPRETATION")

    def load(_=None):
        if not job_dd.value:
            return
        stop_audio()
        R["seg"].clear()
        R["pk"].clear()
        R["path"] = Path(job_dd.value)
        R["data"] = json.loads(R["path"].read_text("utf-8"))
        R["v"] = next((k for k in range(1, R["data"]["verses"] + 1) if flagged(k)), 1)
        rmsg.value = "Loading waveforms (the first time takes a moment)..."
        page.update()

        def go():
            d = R["data"]
            for kind in ("rec", "taf"):
                R["pk"][kind] = core.peaks(d[kind + "_file"], R["path"].parent)
                R["seg"][kind] = core.load_audio(d[kind + "_file"], 24000)
            rmsg.value = ("Fix the ⚠ verses: listen, then click the wave (or use the buttons) to move the "
                          "green START / red END line.  Neighbouring verses are shown in grey.")
            page.update()
            fill_list()
            goto(R["v"])
        threading.Thread(target=go, daemon=True).start()

    job_dd.on_change = load

    def save(build_audio=False):
        d = R["data"]
        if not d:
            return
        d["status"] = "ok" if not any(flagged(k) for k in range(1, d["verses"] + 1)) else "review"
        core.save_json(R["path"], d)
        if not build_audio:
            rmsg.value = "Saved."
            return page.update()
        rmsg.value = "Building the audio..."
        page.update()

        def go():
            try:
                core.assemble_json(d, lambda m: None)
                rmsg.value = f"✓ Built {Path(d['output']).name}" + \
                    ("" if d["status"] == "ok" else "   (some verses are still flagged)")
            except Exception as e:
                rmsg.value = f"✗ Build failed: {e}"
            refresh_jobs()
        threading.Thread(target=go, daemon=True).start()

    def verse_ok(_):
        d, v = R["data"], R["v"]
        if not d:
            return
        d["rec"][v - 1]["flag"] = d["taf"][v - 1]["flag"] = ""
        nxt = next((k for k in list(range(v + 1, d["verses"] + 1)) + list(range(1, v)) if flagged(k)), None)
        fill_list()
        goto(nxt or v)
        if not nxt:
            rmsg.value = "No flagged verses left - press 'Save & build audio'."
            page.update()

    review_tab = ft.Column([
        ft.Row([job_dd, ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh list", on_click=refresh_jobs)]),
        rmsg,
        ft.Row([verse_list, ft.Column([rec_card, taf_card], expand=True, scroll=ft.ScrollMode.AUTO)],
               vertical_alignment=ft.CrossAxisAlignment.START, expand=True),
        ft.Row([ft.FilledButton("✓ This verse is fine → next problem", on_click=verse_ok),
                ft.OutlinedButton("Save", on_click=lambda _: save(False)),
                ft.FilledButton("Save & build audio", icon=ft.Icons.AUDIOTRACK, on_click=lambda _: save(True))])],
        expand=True)

    page.add(ft.Tabs(selected_index=0, expand=True, tabs=[
        ft.Tab(text="1 · Build", content=ft.Container(build_tab, padding=ft.padding.only(top=12))),
        ft.Tab(text="2 · Review problems", content=ft.Container(review_tab, padding=ft.padding.only(top=12)))],
        on_change=lambda e: refresh_jobs() if e.control.selected_index == 1 else None))


if __name__ == "__main__":
    ft.app(target=main)
