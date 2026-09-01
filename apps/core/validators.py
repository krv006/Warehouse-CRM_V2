"""Fayl yuklash xavfsizligi: ruxsat etilgan turlar va hajm chegarasi."""

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

MAX_UPLOAD_MB = 10

# Hujjat va skan fayllari — bajariladigan fayllar (exe, sh, js) qabul qilinmaydi
ALLOWED_UPLOAD_EXTENSIONS = [
    'pdf', 'jpg', 'jpeg', 'png', 'webp',
    'doc', 'docx', 'xls', 'xlsx',
]

document_extension_validator = FileExtensionValidator(
    ALLOWED_UPLOAD_EXTENSIONS,
    message="Bu fayl turi qabul qilinmaydi. Ruxsat: pdf, rasm (jpg/png/webp), doc(x), xls(x).",
)


def validate_upload_size(file):
    """Yuklanayotgan fayl hajmini cheklaydi (xotira va disk himoyasi)."""
    if file.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f'Fayl hajmi {MAX_UPLOAD_MB} MB dan oshmasligi kerak.')
