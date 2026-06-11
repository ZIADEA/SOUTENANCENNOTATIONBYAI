"""Génération de rapports PDF finaux avec ReportLab."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)

from .models import NoteIA
from .pipeline import calculer_note_globale


def generer_rapport_pdf(passage) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2*cm, bottomMargin=2*cm,
        leftMargin=2*cm, rightMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    h1 = styles['Heading1']
    h2 = styles['Heading2']
    normal = styles['Normal']
    petit = ParagraphStyle('petit', parent=normal, fontSize=9, textColor=colors.grey)

    story = []
    session = passage.session
    story.append(Paragraph('Rapport de soutenance — SoutenanceAI', h1))
    story.append(Paragraph(f'<b>Session :</b> {session.titre}', normal))
    story.append(Paragraph(f'<b>Professeur :</b> {session.professeur.get_full_name() or session.professeur.username}', normal))
    story.append(Paragraph(f'<b>Date :</b> {passage.heure_prevue.strftime("%d/%m/%Y %H:%M")}', normal))
    story.append(Paragraph(f'<b>Langue :</b> {session.get_langue_display()}', normal))
    story.append(Paragraph(f'<b>Personnalité IA :</b> {session.get_personnalite_ia_display()}', normal))
    story.append(Spacer(1, 0.5*cm))

    for etu in passage.etudiants.all():
        story.append(Paragraph(f'Étudiant : {etu.get_full_name() or etu.username}', h2))
        notes = NoteIA.objects.filter(
            passage=passage, etudiant=etu,
        ).select_related('critere').order_by('critere__ordre')

        if not notes.exists():
            story.append(Paragraph('<i>Aucune note enregistrée.</i>', normal))
            continue

        data = [['Critère', 'Coef.', 'Note IA', 'Note finale', 'Commentaire']]
        for n in notes:
            data.append([
                Paragraph(n.critere.nom, normal),
                f'{n.critere.coefficient:g}',
                f'{n.note_ia:.1f}/20',
                f'{n.note_finale:.1f}/20',
                Paragraph(
                    (n.commentaire_prof or n.commentaire_ia or '')[:300],
                    petit,
                ),
            ])
        table = Table(data, colWidths=[4.5*cm, 1.3*cm, 1.7*cm, 1.9*cm, 6.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.3*cm))

        globale = calculer_note_globale(passage, etu)
        if globale is not None:
            story.append(Paragraph(
                f'<b>Note globale (moyenne pondérée) : {globale:.2f}/20</b>',
                h2,
            ))
        story.append(Spacer(1, 0.7*cm))

    if passage.transcription:
        story.append(PageBreak())
        story.append(Paragraph('Transcription de la présentation', h2))
        # Découpage en paragraphes
        for paragraphe in passage.transcription.split('\n\n')[:30]:
            if paragraphe.strip():
                story.append(Paragraph(paragraphe[:1000], normal))
                story.append(Spacer(1, 0.1*cm))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
