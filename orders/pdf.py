import io

from xhtml2pdf import pisa


def render_html_to_pdf(html_string):
    """
    Convert an HTML string into PDF bytes using xhtml2pdf.

    Returns the raw PDF bytes, or an empty bytestring if rendering fails.
    """
    output = io.BytesIO()
    pdf_status = pisa.CreatePDF(io.StringIO(html_string), dest=output)

    if pdf_status.err:
        return b""

    return output.getvalue()
