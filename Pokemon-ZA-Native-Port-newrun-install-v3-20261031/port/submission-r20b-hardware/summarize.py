"""Summarize the completed matched-scene r20b experiment from saved evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from analyze_windows import analyze

ROOT = Path(__file__).resolve().parents[2]
H = ROOT / "evidence/submission-r20b-hardware"
SID = "0000066a30a19292"
S = H / ("session-" + SID)
LOG = H / "r20-20261028-194219Z.klog.log"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    phases = []
    for label, seq in (("each-1", 10), ("batch4", 20), ("batch2", 30), ("batch8", 40), ("each-2", 50)):
        d = S / label
        phase = read(d / "phase.json")
        analysis = read(d / f"measure_{seq+2}-analysis.json")
        csv = d / f"measure_{seq+2}.csv"
        assert phase["completed"] and phase["session"] == SID and phase["pid"] == 113
        assert phase["transition"]["result"] == "applied"
        assert phase["transition"]["profile"] == phase["profile"]
        assert phase["measurement"]["ack"]["result"] == "complete"
        assert hashlib.sha256(csv.read_bytes()).hexdigest() == phase["measurement"]["files"][0]["sha256"]
        assert analysis["shader_affected_intervals"] == 0 and analysis["fps_modes"] == [0]
        assert analysis["capture_inside_window"] is False
        windows = analyze(LOG, csv, 0)
        assert windows["profiles"] == [phase["profile"]]
        write(d / "profiler.json", windows)
        phases.append(dict(label=label, profile=phase["profile"], seq=seq,
                           started=phase["at"], completed=phase["completed_at"],
                           timing=analysis["all_intervals"], profiler=windows,
                           shader_affected_intervals=0, fps_mode=0,
                           before_image=phase["before"]["files"][0]["name"],
                           after_image=phase["after"]["files"][0]["name"],
                           visual_review="Same road, camera orientation and 13m Wild Zone 1 gate marker. Idle animations vary. No obvious corruption in reviewed after captures."))
    baseline = sum(p["timing"]["intervals"] for p in (phases[0], phases[-1])) / sum(p["timing"]["duration_s"] for p in (phases[0], phases[-1]))
    gain = (phases[1]["timing"]["interval_rate_fps"] / baseline - 1) * 100
    deploy = read(H / "deploy-20261028-194111Z/receipt.json")
    finish = read(H / "finish-20261028-195423Z/receipt.json")
    identity = read(H / "launch-identity.json")
    assert deploy["installed"] and finish["startup_profile"] == "batch4" and finish["startup_readback_verified"]
    prefixes = ("[zarecomp] [vk] t=", "[zarecomp] [za-r20b-submit]", "[za-r20b-submit]", "[zarecomp] [za-r16]", "[za-observer]", "[zarecomp] radv/ps5 submissions:")
    filtered = [line for line in LOG.read_text(errors="replace").splitlines() if line.startswith(prefixes)]
    (H / "performance-filtered.log").write_text("\n".join(filtered) + "\n", encoding="utf-8")
    result = dict(at=datetime.now(timezone.utc).isoformat(), installed=True, hardware_tested=True,
                  installed_sha256=deploy["new_sha256"], title="PPSA91762", session=SID, pid=113,
                  run=identity["run"], phases=phases, baseline_pooled_fps=baseline,
                  stationary_scene_batch4_gain_percent=gain,
                  stationary_scene_improvement_observed=True, fps_gain_proven=False,
                  fps_gain_proven_scope="No general gameplay or scanout FPS gain established; the stationary present-interval improvement is separately measured above.",
                  sixty_fps_achieved=False, selected_profile="batch4", startup_profile="batch4",
                  finish=finish, save_backup=identity["backup_nas_verified"],
                  save_backup_sha256=identity["save_sha256"], save_written_by_tools=False,
                  save_after_test_verified=False,
                  closure="After measurements, ShellUI Options and AppClosingScene precede KillApp; the title is no longer running. No restart was requested by the tooling.",
                  limitations=["Five 20-second windows, one stationary scene, natural idle animations and NPC activity.",
                               "CPU intervals between presentation submissions, not display scanout or simulation-speed proof.",
                               "All samples use original FPS timing mode 0; no Dynamic60 validation in this experiment.",
                               "Screenshots and file transfers occur outside measurement windows. Profiler remains enabled.",
                               "The startup selection is saved for the next launch; no restart validation was performed after this setting change.",
                               "Profiler timers may overlap; do not add CPU/GPU/wait totals together.",
                               "No post-close save hash comparison: sandbox was already unmounted. The pre-test save is backed up and tools did not write saves."])
    write(H / "final-result.json", result)
    names = ["ללא איחוד — לפני", "קבוצות של 4", "קבוצות של 2", "קבוצות של 8", "ללא איחוד — אחרי"]
    rows = [f"{name}: {p['timing']['interval_rate_fps']:.2f} FPS; p95 {p['timing']['frame_ms']['p95']:.2f} ms; 1% low {p['timing']['one_percent_low_fps']:.2f} FPS" for name, p in zip(names, phases)]
    profrows = [f"{name}: הגשות Vulkan לפריים {p['profiler']['per_frame']['vk_calls']:.2f}; CPU בהגשה {p['profiler']['per_frame']['submit_ms']:.2f} ms; המתנה לחריץ {p['profiler']['per_frame']['ring_ms']:.2f} ms; CPU executor {p['profiler']['per_frame']['exec_ms']:.2f} ms" for name, p in zip(names, phases)]
    text = f"""Pokémon Legends: Z-A Randomizer — תוצאות r20b, 28.10.2026

מותקן ונבדק. נבחר batch4 להמשך ניסיון ונשמר גם להפעלה הבאה.
האיחוד בקבוצות של ארבע שיפר בסצנה זו את הקצב בכ־{gain:.1f}%.
זה שיפור קטן של כפריים לשנייה; אין עדיין 60 FPS ואין הוכחה לשיפור בכל המשחק.

חמש מדידות, 20 שניות בכל מצב, באותו תהליך ובריצה עם Fennekin.
הדמות והמצלמה נשארו מול שער Wild Zone 1 במרחק 13 מטר. תמונות לפני/אחרי
נשמרו והושוו. לא נראתה השחתת תמונה בצילומים שנבדקו; זו בדיקה חזותית מוגבלת.

""" + "\n".join(rows) + f"""

שתי מדידות הביקורת כמעט זהות; בסיס משוקלל {baseline:.3f} FPS.
לא הייתה עבודת שיידרים באף חלון. לא היו פריימים מעל 50 ms בחלונות אלה.
המדד הוא מרווחי CPU בין הגשות Present. הוא אינו מדידת סריקת המסך או מהירות
הסימולציה. כל המצבים נמדדו בתזמון המשחק המקורי (mode 0).
צילום והעברה ברשת נעשו לפני/אחרי המדידות, לא בתוכן.

נתוני פרופיילר, בחלונות מלאים שנמצאים בתוך המדידה:
""" + "\n".join(profrows) + """

הפחתת מספר ההגשות מורידה את זמן ה־CPU שנמדד בתוך ההגשה, אבל חלק מההמתנה
עובר להמתנה לחריצי הפקודות. לכן איחוד אגרסיבי יותר אינו בהכרח מהיר יותר.
קבוצות של שמונה האטו את הסצנה; ארבע היו הטובות מבין המצבים שנבדקו.
אלה הגשות Vulkan, לא איחוד של קריאות הציור עצמן. מספר קריאות הציור כמעט
לא השתנה. טיימרים חופפים ולכן אסור לחבר את זמני CPU/GPU/המתנה זה לזה.

המשך העבודה המוצע: לצמצם הכנה חוזרת של תיאורי משאבים ל־GPU (descriptors),
ואחר כך לבדוק הקלטת פקודות ברקע עם בעלות וסנכרון מוגדרים. במקביל יש להפריד
שיפור זמן הפריים מתיקון תזמון Dynamic60; מוד 60 לבדו אינו מספק תקציב רינדור.

הקישור GameBanana שהמשתמש שלח הוא FPS+GFX RC3.0. הורד הקובץ המדויק
1731160 ונבדק: הוא זהה בבייטים לארכיון המוד שכבר נותח, כולל 40 הקבצים.
זה אינו קוד המקור המקורי של המשחק. דוח המחקר המצורף מפרט את המקורות,
ההתאמות שכבר קיימות בפורט והשינויים שעדיין אפשר לחקור.

השמירה גובתה לפני הבדיקה, כולל אימות SHA-256 ועותק ב־NAS. הכלים לא כתבו
שמירות ולא שינו סיד או נתוני רנדומייזר. לאחר המדידות נסגר המשחק דרך ממשק
המערכת וה־sandbox ירד, ולכן לא בוצעה השוואת hash נוספת של השמירה אחרי סגירה.
מצב batch4 הוחל בזמן הריצה לפי לוג הרינדור, ולאחר הסגירה נשמר בקובץ ההפעלה
ונקרא חזרה לאימות. לא בוצע אתחול נוסף לאימות קריאת ברירת המחדל החדשה.
כלי איסוף הלוגים הופסק בסיום; אין בדיקת קונסולה שרצה ברקע מטעם שלב זה.

לשחזור מצב ההגשה הקודם: submission-options.txt עם each בשורה אחת.
הקובץ הקודם נשמר גם בקונסולה בשם מתוארך before-r20b.
הבינארי r20b עצמו לא שונה לאחר הקישור והאימות.
"""
    (H / "Hardware-results-HE.txt").write_text(text, encoding="utf-8-sig")
    print(json.dumps(dict(baseline_fps=baseline, batch4_gain_percent=gain,
                         phases=[dict(label=p["label"], fps=p["timing"]["interval_rate_fps"], per_frame=p["profiler"]["per_frame"]) for p in phases]), indent=2))


if __name__ == "__main__":
    main()
