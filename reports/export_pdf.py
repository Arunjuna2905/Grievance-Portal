def report_as_text(report):
    """Prepared report content. Replace with a PDF library for production export."""
    return '\n'.join(f'{key.replace("_", " ").title()}: {value}' for key, value in report.items())
