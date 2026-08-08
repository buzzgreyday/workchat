from io import BytesIO
import qrcode

def get_qr_code(url: str) -> bytes:
    img = qrcode.make(url, box_size=5, border=1)

    buffer = BytesIO()
    img.save(buffer, format="PNG")

    return buffer.getvalue()