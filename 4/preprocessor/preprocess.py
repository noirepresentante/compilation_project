import re
import sys
from pathlib import Path

# --- Литералы C/C++ (чтобы не вырезать // и /* */ внутри строк/символов) ---
RE_LITERALS = re.compile(
    r'"(?:\\.|[^"\\])*"'      # "..."
    r"|'(?:\\.|[^'\\])*'"     # '...'
)

# --- Комментарии ---
RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)  # /* ... */ (включая переводы строк)
RE_LINE_COMMENT  = re.compile(r"//.*?$", re.M)     # // ... до конца строки

# --- Пробелы/табы ---
RE_LEAD_WS  = re.compile(r"^[ \t]+", re.M)         # в начале строк
RE_TRAIL_WS = re.compile(r"[ \t]+$", re.M)         # в конце строк
RE_MULTI_WS = re.compile(r"[ \t]{2,}")             # последовательности пробелов/табов

# --- Недопустимые управляющие символы (кроме \n \r \t) ---
RE_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def line_of_pos(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def protect_literals(text: str):
    """Заменяет литералы на плейсхолдеры __LIT_0__, __LIT_1__ ..."""
    mapping = {}
    idx = 0

    def repl(m: re.Match) -> str:
        nonlocal idx
        key = f"__LIT_{idx}__"
        mapping[key] = m.group(0)
        idx += 1
        return key

    return RE_LITERALS.sub(repl, text), mapping


def restore_literals(text: str, mapping: dict) -> str:
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def check_bad_control_chars(text: str) -> list[str]:
    errors = []
    for m in RE_BAD_CTRL.finditer(text):
        errors.append(f"Недопустимый управляющий символ на строке {line_of_pos(text, m.start())}")
    return errors


def check_block_comment_balance(protected_text: str) -> list[str]:
    """
    Проверка незакрытого /* и лишнего */.
    Работает по токенам / * и * / (литералы уже защищены).
    """
    errors = []
    tokens = [(m.start(), m.group(0)) for m in re.finditer(r"/\*|\*/", protected_text)]

    stack = []
    for pos, tok in tokens:
        if tok == "/*":
            stack.append(pos)
        else:  # */
            if not stack:
                errors.append(f"Лишнее закрытие '*/' на строке {line_of_pos(protected_text, pos)}")
            else:
                stack.pop()

    if stack:
        pos = stack[-1]
        errors.append(f"Незакрытый многострочный комментарий '/*' (строка {line_of_pos(protected_text, pos)})")

    return errors


def preprocess_cpp(text: str):
    info, errors = [], []

    # Нормализуем переводы строк
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Проверка недопустимых символов
    errors += check_bad_control_chars(text)

    # Защита строк/символов
    protected, mapping = protect_literals(text)

    # Проверка незакрытого /* ... */
    errors += check_block_comment_balance(protected)
    if errors:
        return "", info, errors

    # Удаляем комментарии regex-ами
    before = len(protected)
    protected = RE_BLOCK_COMMENT.sub("", protected)
    info.append(f"Удалено символов (блок-комментарии): ~{before - len(protected)}")

    before = len(protected)
    protected = RE_LINE_COMMENT.sub("", protected)
    info.append(f"Удалено символов (строковые комментарии): ~{before - len(protected)}")

    # Чистим пробелы/табы
    protected = RE_LEAD_WS.sub("", protected)
    protected = RE_TRAIL_WS.sub("", protected)
    protected = RE_MULTI_WS.sub(" ", protected)

    # Удаляем пустые строки
    lines = protected.split("\n")
    nonempty = [ln for ln in lines if ln.strip() != ""]
    info.append(f"Удалено пустых строк: {len(lines) - len(nonempty)}")
    protected = "\n".join(nonempty).strip() + "\n"

    # Возвращаем литералы
    cleaned = restore_literals(protected, mapping)
    return cleaned, info, errors


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Использование: python preprocess.py <input.cpp> [-o output.cpp]")
        return 2

    inp = Path(argv[1])
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    if not inp.exists():
        print(f"[ERROR] Файл не найден: {inp}")
        return 2

    try:
        text = inp.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("[ERROR] Не удалось прочитать файл как UTF-8")
        return 2

    cleaned, info, errors = preprocess_cpp(text)

    for m in info:
        print("[INFO]", m)

    if errors:
        for e in errors:
            print("[ERROR]", e, file=sys.stderr)
        print("Обнаружены ошибки — вывод очищенного кода отменён.", file=sys.stderr)
        return 1

    if out:
        out.write_text(cleaned, encoding="utf-8")
        print(f"[INFO] Очищенный код сохранён в: {out}")
    else:
        print("\n--- CLEANED ---")
        print(cleaned, end="")

    print("Ошибок не выявлено")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
