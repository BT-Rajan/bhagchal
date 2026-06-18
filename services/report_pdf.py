"""
Builds the Cogzi-branded behavioral assessment PDF from a game report and
the structured profile returned by services.analysis_service.analyze_report.

The two opening paragraphs are deterministic (built in code, not by the
model) so the required wording/branding is guaranteed regardless of what
the model returns:

  1. "Based on the game <game_id> played on <date & time>, evidenced
     through <game_id>.json, the following report is generated using
     Cogzi Behavioral Intelligence Model Version 1.0."
  2. "The model has observed the following traits in <username> ...
     aligns with the expectations set by <Job_Description_id> ... the
     match is <%>. This is based on limited samples, ask Admin for more
     samples to get more precise results."

Everything else (decision style, strengths, weaknesses, temperament,
adaptability, overall assessment) is the model's own analysis, laid out
into consistent sections rather than relying on the model to format its
own prose.
"""
import os
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
)

from config import Config


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(
        name='CogziTitle', parent=base['Title'], fontSize=20, spaceAfter=4,
        textColor=colors.HexColor('#1a2b3c')
    ))
    base.add(ParagraphStyle(
        name='CogziSubtitle', parent=base['Normal'], fontSize=11,
        textColor=colors.HexColor('#6b7280'), spaceAfter=18
    ))
    base.add(ParagraphStyle(
        name='CogziSection', parent=base['Heading2'], fontSize=13,
        textColor=colors.HexColor('#1a2b3c'), spaceBefore=14, spaceAfter=6
    ))
    base.add(ParagraphStyle(
        name='CogziBody', parent=base['Normal'], fontSize=10.5, leading=15
    ))
    base.add(ParagraphStyle(
        name='CogziDisclaimer', parent=base['Normal'], fontSize=8.5,
        textColor=colors.HexColor('#6b7280'), spaceBefore=18
    ))
    return base


def _format_when(report):
    raw = report.get('start_time') or report.get('end_time')
    if not raw:
        return 'an unspecified date'
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except (TypeError, ValueError):
        return str(raw)


def generate_pdf_report(report, profile, output_path):
    """Render the behavioral assessment PDF. Returns output_path."""
    game_id = report.get('game_id', 'unknown')
    username = report.get('username', 'the player')
    when = _format_when(report)
    traits = profile.get('traits', [])
    traits_text = ', '.join(traits) if traits else 'no distinct traits identified'
    match_pct = profile.get('match_percentage', 0)

    styles = _styles()
    story = []

    story.append(Paragraph('Cogzi Behavioral Intelligence Report', styles['CogziTitle']))
    story.append(Paragraph(Config.COGZI_MODEL_NAME, styles['CogziSubtitle']))

    intro = (
        f"Based on the game {game_id} played on {when}, evidenced through "
        f"{game_id}.json, the following report is generated using "
        f"{Config.COGZI_MODEL_NAME}."
    )
    story.append(Paragraph(intro, styles['CogziBody']))
    story.append(Spacer(1, 8))

    trait_para = (
        f"The model has observed the following traits in {username}: "
        f"<b>{traits_text}</b>. These traits align with the expectations set by "
        f"{Config.JOB_DESCRIPTION_ID} as per {Config.COGZI_MODEL_NAME}. "
        f"The match is <b>{match_pct}%</b>. This is based on limited samples; "
        f"ask Admin for more samples to get more precise results."
    )
    story.append(Paragraph(trait_para, styles['CogziBody']))
    story.append(Spacer(1, 10))

    # Game summary table
    final = report.get('final_state', {})
    summary_rows = [
        ['Game ID', game_id, 'Result', report.get('status', '-')],
        ['Role Played', report.get('human_role', '-'), 'Mode', report.get('mode', '-')],
        ['Difficulty', report.get('difficulty', '-'), 'Total Moves', str(report.get('total_moves', '-'))],
        ['Duration (s)', str(report.get('duration_seconds', '-')), 'Goats Captured', str(final.get('goats_captured', '-'))],
    ]
    table = Table(summary_rows, colWidths=[1.3 * inch, 1.7 * inch, 1.3 * inch, 1.7 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef2f7')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#eef2f7')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    def add_section(title, content):
        story.append(Paragraph(title, styles['CogziSection']))
        if isinstance(content, list):
            items = [ListItem(Paragraph(str(c), styles['CogziBody']), leftIndent=10) for c in content]
            story.append(ListFlowable(items, bulletType='bullet', start='•'))
        else:
            story.append(Paragraph(str(content), styles['CogziBody']))

    add_section('Decision-Making Style', profile.get('decision_style', '-'))
    add_section('Strengths', profile.get('strengths', []))
    add_section('Weaknesses', profile.get('weaknesses', []))
    add_section('Temperament &amp; Emotional Traits', profile.get('temperament', '-'))
    add_section('Pattern Recognition &amp; Adaptability', profile.get('adaptability', '-'))
    add_section('Overall Assessment', profile.get('overall_assessment', '-'))

    story.append(Paragraph(
        f"Generated by {Config.COGZI_MODEL_NAME} &mdash; Confidential. "
        "This assessment is derived from gameplay telemetry only and should be "
        "considered indicative, not definitive.",
        styles['CogziDisclaimer']
    ))

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch
    )
    doc.build(story)
    return output_path
