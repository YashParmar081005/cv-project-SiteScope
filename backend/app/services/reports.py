"""Downloadable PDF progress report (ReportLab), built only from stored records."""
from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape as _esc

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .storage import LocalStorage

ACCENT = colors.HexColor("#d97706")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
GRID = colors.HexColor("#e5e7eb")


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=18, textColor=INK, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                             textColor=INK, spaceAfter=1, keepWithNext=1),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9, leading=12, textColor=INK),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=7.5, leading=9.5, textColor=INK),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=7.5, leading=10, textColor=MUTED),
    }


def _table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef3c7"))]
    t.setStyle(TableStyle(style))
    return t


def _chart(snapshots: list[dict], planned: list[dict]) -> Drawing:
    width, height = 170 * mm, 62 * mm
    d = Drawing(width, height)
    as_date = lambda v: date.fromisoformat(str(v)[:10])  # noqa: E731
    dates = [as_date(p["date"]) for p in planned] + [as_date(s["as_of_date"]) for s in snapshots]
    if not dates:
        d.add(String(10, height / 2, "No planned schedule or confirmed progress to chart.", fontSize=9, fillColor=MUTED))
        return d
    origin = min(dates)
    series, names = [], []
    if planned:
        series.append([((as_date(p["date"]) - origin).days, p["progress"] * 100) for p in planned])
        names.append(("Planned schedule", colors.HexColor("#9ca3af")))
    if snapshots:
        points = [((as_date(s["as_of_date"]) - origin).days, s["progress"] * 100) for s in snapshots]
        series.append(points * 2 if len(points) == 1 else points)
        names.append(("Confirmed progress", ACCENT))
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 12 * mm, 10 * mm, width - 20 * mm, height - 18 * mm
    lp.data = series
    lp.yValueAxis.valueMin, lp.yValueAxis.valueMax, lp.yValueAxis.valueStep = 0, 100, 25
    lp.yValueAxis.labelTextFormat = "%d%%"
    lp.xValueAxis.labelTextFormat = lambda v: date.fromordinal(origin.toordinal() + int(v)).strftime("%b %y")
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 7
    for i, (name, colour) in enumerate(names):
        lp.lines[i].strokeColor, lp.lines[i].strokeWidth = colour, 1.6
        if name.startswith("Confirmed"):
            lp.lines[i].symbol = makeMarker("FilledCircle", size=4, fillColor=colour)
        else:
            lp.lines[i].strokeDashArray = [3, 2]
        d.add(String(14 * mm + i * 60 * mm, height - 5 * mm, f"— {name}", fontSize=7.5, fillColor=colour))
    d.add(lp)
    return d


def build_pdf(*, project: dict, summary: dict, progress: dict, forecast: dict, observations: list[dict],
              storage: LocalStorage, generated_by: str) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Progress report — {project['name']}", author="SiteScope")
    story = [Paragraph(_esc(f"Progress report — {project['name']}"), s["h1"]),
             Paragraph(_esc(f"{project['construction_type'].replace('_', ' ').title()} · {project.get('location') or 'no location'} · "
                            f"generated {date.today().isoformat()} by {generated_by}"), s["small"])]
    if project.get("description"):
        story.append(Paragraph(_esc(project["description"]), s["body"]))

    fc = forecast
    rows = [["Item", "Value"],
            ["Planned start → planned finish", f"{project['planned_start_date']} → {project['target_completion_date']}"],
            ["Progress (from confirmed photo stages)", f"{_pct(summary['progress'])} on {summary['progress_date']}" if summary["progress"] is not None else "—"],
            ["Estimated completion", fc.get("estimated_completion_date") or fc["status"].replace("_", " ")],
            ["Estimate range", f"{fc['range']['earliest']} – {fc['range']['latest']}" if fc.get("range") else "—"],
            ["Confidence", fc["confidence"]],
            ["Photos", str(summary["photos"])]]
    story += [Paragraph("Summary", s["h2"]), _table(rows, [70 * mm, 100 * mm])]
    story += [Paragraph("Progress vs plan", s["h2"]), _chart(progress["snapshots"], progress["planned_curve"]["points"])]

    stage_rows = [["Stage", "Weight", "Planned window"]]
    stage_rows += [[m["name"], f"{m['weight']:.0%}", f"{m.get('planned_start') or '—'} → {m.get('planned_end') or '—'}"]
                   for m in project["milestones"]]
    story += [Paragraph("Stages", s["h2"]), _table(stage_rows, [70 * mm, 25 * mm, 75 * mm])]

    story.append(Paragraph("How the estimate was made", s["h2"]))
    story += [Paragraph(f"• {x}", s["small"]) for x in fc.get("assumptions", []) + fc.get("warnings", [])]

    if observations:
        story.append(Paragraph("Latest photos", s["h2"]))
        for o in observations[:4]:
            img = _image(storage, o["original"]["storage_key"], 62 * mm, 70 * mm, s)
            cv = o.get("summary") or {}
            review = o.get("stage_review")
            changed = cv.get("changed_area_share")
            text = [Paragraph(f"<b>{o['capture_date']}</b>", s["body"]),
                    Paragraph(f"Computer vision: {cv.get('phase') or 'no phase'} ({cv.get('confidence') or '—'} confidence)"
                              + (f", {changed:.1%} of the area changed since the previous photo" if changed is not None else ""), s["small"]),
                    Paragraph(f"Confirmed stage: {review['stage_key'].replace('_', ' ')}"
                              f"{'' if review.get('stage_progress') is None else ' ' + str(review['stage_progress']) + '%'}"
                              if review else "Stage not confirmed", s["small"])]
            story.append(KeepTogether([_table([[img, text]], [66 * mm, 104 * mm], header=False), Spacer(1, 3)]))
    doc.build(story)
    return buf.getvalue()


def _image(storage: LocalStorage, key: str, max_w: float, max_h: float, s: dict):
    try:
        img = Image(io.BytesIO(storage.get(key)))
        ratio = img.imageHeight / img.imageWidth
        img.drawWidth = min(max_w, max_h / ratio)
        img.drawHeight = img.drawWidth * ratio
        return img
    except Exception:
        return Paragraph("(image unavailable)", s["small"])


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(_fmt(x) for x in v)
    return "—" if v is None else str(v)


def build_analysis_pdf(*, project: dict, obs: dict, detail: dict, asset_keys: dict, storage: LocalStorage,
                       generated_by: str) -> bytes:
    """One photo: result, every pipeline step (image, algorithm, parameters, measurements), how the answer was found."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Photo analysis — {project['name']} {obs['capture_date']}", author="SiteScope")
    width = A4[0] - 32 * mm
    story = [Paragraph(_esc(f"Photo analysis — {project['name']}"), s["h1"]),
             Paragraph(_esc(f"Photo taken {obs['capture_date']} · {obs['original'].get('filename') or ''} · "
                            f"report generated {date.today().isoformat()} by {generated_by}"), s["small"]), Spacer(1, 6),
             _image(storage, obs["original"]["storage_key"], width, 95 * mm, s)]

    result = detail.get("result")
    rows = [["Item", "Value"]]
    if result:
        used, fc = result["used"], result["forecast"]
        rows += [["Construction stage", f"{used['stage_name']} · "
                  + ("% unknown" if used["stage_progress"] is None else f"{used['stage_progress']} %")
                  + (" (confirmed by user)" if used["source"] == "confirmed" else " (computer-vision suggestion)")],
                 ["Overall progress", _pct(result["progress"])],
                 ["Estimated completion", fc.get("estimated_completion_date") or fc["status"].replace("_", " ")],
                 ["Range", f"{fc['range']['earliest']} – {fc['range']['latest']}" if fc.get("range") else "—"],
                 ["Planned finish", project["target_completion_date"]], ["Confidence", fc["confidence"]]]
    else:
        rows.append(["Result", obs.get("analysis_error") or "no stage could be determined"])
    story += [Paragraph("Result", s["h2"]), _table(rows, [55 * mm, width - 55 * mm])]

    analysis = detail.get("analysis") or {}
    # Each section heading goes inside its first block: ReportLab's keepWithNext cannot chain into a KeepTogether.
    heading = [Paragraph("Computer-vision pipeline: every step this photo passed through", s["h2"])]
    for step in analysis.get("steps", []):
        block = heading + [Paragraph(_esc(f"Step {step['number']} — {step['title']}"), s["h3"]),
                           Paragraph(f"<b>Algorithm:</b> {_esc(step['algorithm'])}", s["small"]),
                           Paragraph(f"<b>Why:</b> {_esc(step['purpose'])}", s["small"])]
        if step["params"]:
            block.append(Paragraph("<b>Parameters:</b> " + _esc("; ".join(f"{k} = {_fmt(v)}" for k, v in step["params"].items())), s["small"]))
        if step["metrics"]:
            block.append(Paragraph("<b>Measured:</b> " + _esc("; ".join(f"{k} = {_fmt(v)}" for k, v in step["metrics"].items())), s["small"]))
        if step.get("asset_id") in asset_keys:
            block += [Spacer(1, 3), _image(storage, asset_keys[step["asset_id"]], width, 82 * mm, s)]
        story.append(KeepTogether(block + [Spacer(1, 8)]))
        heading = []

    heading = [Paragraph("How we got the answer", s["h2"])]
    for section in detail.get("explanation", []):
        part = heading + [Paragraph(_esc(section["title"]), s["h3"]), Paragraph(_esc(section["text"]), s["small"])]
        if section.get("rows"):
            widths = [42 * mm, 78 * mm, width - 120 * mm] if section.get("key") == "pipeline" else [45 * mm, 25 * mm, width - 70 * mm]
            cells = [[Paragraph(_esc(str(c)), s["cell"]) for c in r] for r in section["rows"]]
            part.append(_table(cells, widths, header=False))
        story.append(KeepTogether(part + [Spacer(1, 5)]))
        heading = []
    doc.build(story)
    return buf.getvalue()
