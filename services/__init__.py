"""Services package - Business logic."""

from .engine import (
    GameEngine,
    init_state,
    node_label,
    format_move,
    format_moves_list
)
from .ai import AIService
from .report import ReportService
from .analysis_service import analyze_report, AnalysisError
from .report_pdf import generate_pdf_report
from .mailer import send_report_email, MailError

__all__ = [
    'GameEngine',
    'init_state',
    'node_label',
    'format_move',
    'format_moves_list',
    'AIService',
    'ReportService',
    'analyze_report',
    'AnalysisError',
    'generate_pdf_report',
    'send_report_email',
    'MailError'
]
