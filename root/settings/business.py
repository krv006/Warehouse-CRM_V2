"""TZ dagi biznes qoidalari — bir joyda turadigan raqamlar."""

# Oldindan to'lov: 1 mlrd dan kam bo'lsa 30%, ko'p bo'lsa 15%
PREPAYMENT_THRESHOLD = 1_000_000_000
PREPAYMENT_PERCENT_SMALL = 30
PREPAYMENT_PERCENT_LARGE = 15

# Muddatning oxirgi shuncha kuni qizil rangda ko'rsatiladi
DEADLINE_RED_ZONE_DAYS = 10

# Sotuv (shartnoma) qatorlari uchun standart QQS foizi.
# Kirim (to'ldirish) tomonida default 0 — buyurtmachi ta'minotchi
# hisobiga qarab o'zi kiritadi.
DEFAULT_VAT_PERCENT = 12
