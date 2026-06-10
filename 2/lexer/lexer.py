from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# Подключаем ЛР1, чтобы можно было использовать готовую очистку кода.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from preprocessor.preprocess import preprocess_cpp  # noqa: E402


KEYWORDS = {
    "int",
    "return",
    "bool",
    "if",
    "for",
    "double",
    "const",
    "long",
    "static_cast",
    "while",
    "else",
    "char",
}

BOOL_CONSTANTS = {"false", "true"}

ALLOWED_IDENTIFIERS = {
    "add",
    "x",
    "y",
    "isPrime",
    "n",
    "i",
    "average",
    "std",
    "vector",
    "v",
    "empty",
    "sum",
    "size",
    "factorial",
    "result",
    "main",
    "a",
    "b",
    "c",
    "ok",
    "cout",
    "nums",
    "push_back",
    "s",
    "string",
    "tricky",
    "quote",
}

UNSUPPORTED_KEYWORDS = {
    "switch",
    "case",
    "break",
    "continue",
    "do",
    "float",
    "void",
    "namespace",
    "sizeof",
}

OPERATORS = {
    "+",
    "<=",
    "==",
    "%",
    "=",
    "*",
    "+=",
    "::",
    "<",
    ">",
    "&",
    ".",
    "/",
    "*=",
    "++",
    "-",
    "&&",
    "!=",
    "||",
    "!",
    "<<",
}

DELIMITERS = {
    "(",
    ",",
    ")",
    "{",
    ";",
    "}",
    ":",
}

MULTI_CHAR_OPERATORS = sorted(
    [op for op in OPERATORS if len(op) > 1], key=len, reverse=True
)
SINGLE_CHAR_OPERATORS = {op for op in OPERATORS if len(op) == 1}
SINGLE_CHAR_DELIMITERS = DELIMITERS
OPERATOR_CHARS = set("+-*/%=<>!&|^~?:")
DECLARATION_KEYWORDS = {"int", "double", "bool", "char", "long", "const"}

IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INT_RE = re.compile(r"\d+")
# FLOAT_RE = re.compile(r"\d+\.\d+")
FLOAT_RE = re.compile(r"\d+\.\d*")

KEYWORD_COMMENTS = {
    "int": "Целочисленный тип",
    "double": "Вещественный тип",
    "bool": "Логический тип",
    "char": "Символьный тип",
    "long": "Модификатор размера целого типа",
    "const": "Модификатор неизменяемого объекта",
    "if": "Условный оператор",
    "else": "Альтернативная ветка условия",
    "for": "Цикл с параметром",
    "while": "Цикл с предусловием",
    "return": "Возврат значения из функции",
    "static_cast": "Явное приведение типа",
}

OPERATOR_COMMENTS = {
    "::": "Оператор разрешения области видимости",
    "<<": "Оператор сдвига/потокового вывода",
    "<=": "Меньше или равно",
    ">=": "Больше или равно",
    "==": "Проверка равенства",
    "!=": "Проверка неравенства",
    "&&": "Логическое И",
    "||": "Логическое ИЛИ",
    "++": "Инкремент",
    "--": "Декремент",
    "+=": "Сложение с присваиванием",
    "-=": "Вычитание с присваиванием",
    "*=": "Умножение с присваиванием",
    "/=": "Деление с присваиванием",
    "%=": "Остаток с присваиванием",
    "=": "Присваивание",
    "+": "Сложение",
    "-": "Вычитание",
    "*": "Умножение",
    "/": "Деление",
    "%": "Остаток от деления",
    "<": "Меньше",
    ">": "Больше",
    "!": "Логическое отрицание",
    "&": "Ссылка/побитовое И",
    ".": "Оператор доступа к члену объекта",
}

DELIMITER_COMMENTS = {
    "(": "Открывающая круглая скобка",
    ")": "Закрывающая круглая скобка",
    "{": "Открывающая фигурная скобка",
    "}": "Закрывающая фигурная скобка",
    "[": "Открывающая квадратная скобка",
    "]": "Закрывающая квадратная скобка",
    ";": "Конец оператора",
    ",": "Разделитель элементов",
    ":": "Разделитель/метка диапазона",
}


@dataclass
class Token:
    type: str
    value: str
    line: int
    column: int


@dataclass
class LexicalError:
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"Строка {self.line}, столбец {self.column}: {self.message}"


class Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.errors: List[LexicalError] = []
        self.info: List[str] = []

    def current_char(self) -> str | None:
        if self.pos >= self.length:
            return None
        return self.text[self.pos]

    def peek(self, offset: int = 1) -> str | None:
        idx = self.pos + offset
        if idx >= self.length:
            return None
        return self.text[idx]

    def advance(self, steps: int = 1) -> None:
        for _ in range(steps):
            if self.pos >= self.length:
                return
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1

    def add_token(self, token_type: str, value: str, line: int, column: int) -> None:
        self.tokens.append(Token(token_type, value, line, column))

    def add_error(self, message: str, line: int, column: int) -> None:
        self.errors.append(LexicalError(message, line, column))

    def skip_whitespace(self) -> None:
        while (ch := self.current_char()) is not None and ch.isspace():
            self.advance()

    def skip_preprocessor_directive(self) -> None:
        start_line = self.line
        while (ch := self.current_char()) is not None and ch != "\n":
            self.advance()
        self.info.append(f"Пропущена директива препроцессора на строке {start_line}")

    def read_identifier_or_keyword(self) -> None:
        start_pos = self.pos
        line, column = self.line, self.column
        while (ch := self.current_char()) is not None and (ch.isalnum() or ch == "_"):
            self.advance()
        value = self.text[start_pos:self.pos]

        if value in BOOL_CONSTANTS:
            self.add_token("CONSTANT_BOOL", value, line, column)
        elif value in KEYWORDS:
            self.add_token("KEYWORD", value, line, column)
        elif value in UNSUPPORTED_KEYWORDS:
            self.add_error(
                f"Неподдерживаемое ключевое слово '{value}': лексема отсутствует в таблице ключевых слов для данного подмножества C++",
                line,
                column,
            )
        elif value in ALLOWED_IDENTIFIERS:
            self.add_token("IDENTIFIER", value, line, column)
        else:
            self.add_error(
                f"Неизвестный идентификатор '{value}': лексема отсутствует в таблице идентификаторов для данного подмножества C++",
                line,
                column,
            )

    def read_string_literal(self, quote: str) -> None:
        line, column = self.line, self.column
        start_pos = self.pos
        self.advance()  # opening quote

        escaped = False
        while True:
            ch = self.current_char()
            if ch is None:
                self.add_error("Незакрытый строковый/символьный литерал", line, column)
                return
            if ch == "\n" and not escaped:
                self.add_error("Незакрытый строковый/символьный литерал", line, column)
                return
            if escaped:
                escaped = False
                self.advance()
                continue
            if ch == "\\":
                escaped = True
                self.advance()
                continue
            if ch == quote:
                self.advance()
                value = self.text[start_pos:self.pos]
                self.add_token("CONSTANT_STRING", value, line, column)
                return
            self.advance()

    def is_identifier_context(self) -> bool:
        if not self.tokens:
            return False

        prev = self.tokens[-1]
        if prev.type == "KEYWORD" and prev.value in DECLARATION_KEYWORDS:
            return True
        if prev.type == "DELIMITER" and prev.value in {",", "("}:
            return True
        return False

    def is_number_prefix_context(self) -> bool:
        if not self.tokens:
            return True

        prev = self.tokens[-1]
        if prev.type == "OPERATOR":
            return True
        if prev.type == "KEYWORD":
            return True
        if prev.type == "DELIMITER" and prev.value in {"(", "{", ",", ";", ":"}:
            return True
        return False

    def read_number(self, started_with_dot: bool = False, started_with_comma: bool = False) -> None:
        line, column = self.line, self.column
        start_pos = self.pos
        seen_dot = started_with_dot

        if started_with_dot or started_with_comma:
            self.advance()

        while True:
            ch = self.current_char()
            if ch is None:
                break
            if ch.isdigit():
                self.advance()
                continue
            if ch == ".":
                if seen_dot:
                    self.advance()
                    while (tail := self.current_char()) is not None and (tail.isalnum() or tail in "._"):
                        self.advance()
                    bad = self.text[start_pos:self.pos]
                    self.add_error(
                        f"Некорректно оформленное число '{bad}': несколько точек в константе",
                        line,
                        column,
                    )
                    return
                seen_dot = True
                self.advance()
                continue
            if ch == ",":
                self.advance()
                while (tail := self.current_char()) is not None and tail.isdigit():
                    self.advance()
                bad = self.text[start_pos:self.pos]
                self.add_error(
                    f"Некорректно оформленное число '{bad}': в вещественной константе используется запятая вместо точки",
                    line,
                    column,
                )
                return
            if ch.isalpha() or ch == "_":
                if not seen_dot and self.is_identifier_context():
                    while (tail := self.current_char()) is not None and (tail.isalnum() or tail == "_"):
                        self.advance()
                    bad = self.text[start_pos:self.pos]
                    self.add_error(
                        f"Идентификатор не может начинаться с цифры: '{bad}'",
                        line,
                        column,
                    )
                    return

                while (tail := self.current_char()) is not None and (tail.isalnum() or tail in "._"):
                    self.advance()
                bad = self.text[start_pos:self.pos]
                self.add_error(
                    f"Некорректная числовая константа '{bad}': после цифр не допускаются буквы или '_'",
                    line,
                    column,
                )
                return
            break

        value = self.text[start_pos:self.pos]
        if value == ".":
            self.add_token("OPERATOR", value, line, column)
            return

        if value == ",":
            self.add_token("DELIMITER", value, line, column)
            return
            
        """
        if value.endswith("."):
            self.add_error(
                f"Некорректно оформленное число '{value}': отсутствуют цифры после точки",
                line,
                column,
            )
            return
        """

        if started_with_dot:
            self.add_error(
                f"Некорректно оформленное число '{value}': число не может начинаться с точки",
                line,
                column,
            )
            return

        if started_with_comma:
            self.add_error(
                f"Некорректно оформленное число '{value}': число не может начинаться с запятой",
                line,
                column,
            )
            return

        if FLOAT_RE.fullmatch(value):
            self.add_token("CONSTANT_FLOAT", value, line, column)
        elif INT_RE.fullmatch(value):
            self.add_token("CONSTANT_INT", value, line, column)
        else:
            self.add_error(f"Неизвестный числовой формат '{value}'", line, column)

    def read_operator_or_delimiter(self) -> bool:
        line, column = self.line, self.column

        for op in MULTI_CHAR_OPERATORS:
            if self.text.startswith(op, self.pos):
                self.add_token("OPERATOR", op, line, column)
                self.advance(len(op))
                return True

        ch = self.current_char()
        if ch in SINGLE_CHAR_OPERATORS:
            self.add_token("OPERATOR", ch, line, column)
            self.advance()
            return True

        if ch in SINGLE_CHAR_DELIMITERS:
            self.add_token("DELIMITER", ch, line, column)
            self.advance()
            return True

        if ch in OPERATOR_CHARS:
            start_pos = self.pos
            while (tail := self.current_char()) is not None and tail in OPERATOR_CHARS:
                self.advance()
            bad = self.text[start_pos:self.pos]
            self.add_error(f"Неизвестный оператор '{bad}'", line, column)
            return True

        return False

    def tokenize(self) -> Tuple[List[Token], List[LexicalError], List[str]]:
        while self.pos < self.length:
            ch = self.current_char()
            if ch is None:
                break

            if ch.isspace():
                self.skip_whitespace()
                continue

            if ch == "#":
                self.skip_preprocessor_directive()
                continue

            if ch.isalpha() or ch == "_":
                self.read_identifier_or_keyword()
                continue

            if ch.isdigit():
                self.read_number()
                continue

            if ch == "." and (next_ch := self.peek()) is not None and next_ch.isdigit() and self.is_number_prefix_context():
                self.read_number(started_with_dot=True)
                continue

            if ch == "," and (next_ch := self.peek()) is not None and next_ch.isdigit() and self.is_number_prefix_context():
                self.read_number(started_with_comma=True)
                continue

            if ch in {'"', "'"}:
                self.read_string_literal(ch)
                continue

            if self.read_operator_or_delimiter():
                continue

            bad_line, bad_col = self.line, self.column
            self.add_error(f"Недопустимый символ '{ch}'", bad_line, bad_col)
            self.advance()

        return self.tokens, self.errors, self.info


CATEGORY_ORDER = [
    "KEYWORDS",
    "IDENTIFIERS",
    "INTEGER_CONSTANTS",
    "FLOAT_CONSTANTS",
    "STRING_CONSTANTS",
    "BOOL_CONSTANTS",
    "OPERATORS",
    "DELIMITERS",
]


def build_lexeme_tables(tokens: List[Token]) -> Dict[str, List[str]]:
    tables = {name: [] for name in CATEGORY_ORDER}
    seen = {name: set() for name in CATEGORY_ORDER}

    mapping = {
        "KEYWORD": "KEYWORDS",
        "IDENTIFIER": "IDENTIFIERS",
        "CONSTANT_INT": "INTEGER_CONSTANTS",
        "CONSTANT_FLOAT": "FLOAT_CONSTANTS",
        "CONSTANT_STRING": "STRING_CONSTANTS",
        "CONSTANT_BOOL": "BOOL_CONSTANTS",
        "OPERATOR": "OPERATORS",
        "DELIMITER": "DELIMITERS",
    }

    for token in tokens:
        bucket = mapping[token.type]
        if token.value not in seen[bucket]:
            seen[bucket].add(token.value)
            tables[bucket].append(token.value)

    return tables


def comment_for(category: str, lexeme: str) -> str:
    if category == "KEYWORDS":
        return KEYWORD_COMMENTS.get(lexeme, "Ключевое слово языка")
    if category == "OPERATORS":
        return OPERATOR_COMMENTS.get(lexeme, "Оператор")
    if category == "DELIMITERS":
        return DELIMITER_COMMENTS.get(lexeme, "Разделитель")
    if category == "IDENTIFIERS":
        return "Идентификатор, встречающийся в test.cpp"
    if category == "INTEGER_CONSTANTS":
        return "Целочисленная константа"
    if category == "FLOAT_CONSTANTS":
        return "Вещественная константа"
    if category == "STRING_CONSTANTS":
        return "Строковый или символьный литерал"
    if category == "BOOL_CONSTANTS":
        return "Булева константа"
    return ""


def format_token_table(tokens: List[Token]) -> str:
    header = f"{'Лексема':<28} | {'Тип':<16}"
    sep = "-" * len(header)
    rows = [header, sep]
    for t in tokens:
        rows.append(f"{t.value:<28} | {t.type:<16}")
    return "\n".join(rows)


def format_sequence(tokens: List[Token]) -> str:
    items = []
    for t in tokens:
        value_repr = json.dumps(t.value, ensure_ascii=False)
        items.append(f"({t.type}, {value_repr})")
    return "[" + ", ".join(items) + "]"


def format_sequence_json(tokens: List[Token]) -> str:
    payload = [{"type": t.type, "value": t.value} for t in tokens]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_lexeme_tables(tables: Dict[str, List[str]]) -> str:
    titles = {
        "KEYWORDS": "Таблица 1 – Ключевые слова",
        "IDENTIFIERS": "Таблица 2 – Идентификаторы",
        "INTEGER_CONSTANTS": "Таблица 3 – Целочисленные константы",
        "FLOAT_CONSTANTS": "Таблица 4 – Вещественные константы",
        "STRING_CONSTANTS": "Таблица 5 – Строковые константы",
        "BOOL_CONSTANTS": "Таблица 6 – Булевы константы",
        "OPERATORS": "Таблица 7 – Операторы",
        "DELIMITERS": "Таблица 8 – Разделители",
    }

    sections = []
    for category in CATEGORY_ORDER:
        sections.append(titles[category])
        sections.append(f"{'id':<4} | {'Лексема':<24} | Комментарий")
        sections.append("-" * 72)
        values = tables[category]
        if not values:
            sections.append("— | — | В тестовой программе не встретились")
        else:
            for idx, lexeme in enumerate(values, start=1):
                sections.append(f"{idx:<4} | {lexeme:<24} | {comment_for(category, lexeme)}")
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


LEXEME_BOUNDARY_RULES = """
Правила разделения лексем (для используемого подмножества C++):
1. Ключевые слова и идентификаторы отделяются пробелами, переводами строк,
   операторами или разделителями.
2. Операторы могут примыкать к идентификаторам и константам без пробелов:
   a=b+2, i<=20, !ok, sum+=x.
3. Составные операторы распознаются по принципу максимального совпадения:
   сначала ::, <<, <=, ==, !=, &&, ||, ++, += и т.д., затем односимвольные.
4. Разделители сами образуют границы лексем: (), {}, [], ; , :.
5. Целые и вещественные константы начинаются с цифры. Если после цифр идут буквы,
   подчёркивание или несколько точек, это считается лексической ошибкой.
6. Строковые и символьные литералы заключаются в кавычки и допускают экранирование.
7. Строки, начинающиеся с #, считаются директивами препроцессора и пропускаются,
   так как в ЛР2 анализируются конструкции программы после этапа очистки.
""".strip()


def analyze_text(text: str) -> Tuple[List[Token], List[LexicalError], List[str], Dict[str, List[str]]]:
    lexer = Lexer(text)
    tokens, errors, info = lexer.tokenize()
    tables = build_lexeme_tables(tokens)
    return tokens, errors, info, tables


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Лексический анализатор для подмножества C++, используемого в test.cpp"
    )
    parser.add_argument("input", help="Путь к входному .cpp файлу")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Сначала пропустить исходный код через ЛР1 (preprocessor/preprocess.py)",
    )
    parser.add_argument(
        "--save-cleaned",
        help="Куда сохранить очищенный код, если указан --raw",
    )
    parser.add_argument(
        "--out-tables",
        help="Куда сохранить таблицы лексем",
    )
    parser.add_argument(
        "--out-tokens",
        help="Куда сохранить таблицу токенов",
    )
    parser.add_argument(
        "--out-sequence",
        help="Куда сохранить JSON-последовательность токенов",
    )
    parser.add_argument(
        "--show-info",
        action="store_true",
        help="Показывать информационные сообщения (например, о пропущенных директивах #include)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Файл не найден: {input_path}", file=sys.stderr)
        return 2

    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("[ERROR] Не удалось прочитать файл как UTF-8", file=sys.stderr)
        return 2

    if args.raw:
        cleaned, prep_info, prep_errors = preprocess_cpp(text)
        if args.show_info:
            for msg in prep_info:
                print(f"[PREPROCESSOR] {msg}")
        if prep_errors:
            for err in prep_errors:
                print(f"[ERROR] {err}", file=sys.stderr)
            print("Лексический анализ отменён: препроцессор обнаружил ошибки.", file=sys.stderr)
            return 1
        text = cleaned
        if args.save_cleaned:
            Path(args.save_cleaned).write_text(cleaned, encoding="utf-8")
            print(f"[INFO] Очищенный код сохранён в: {args.save_cleaned}")

    tokens, errors, info, tables = analyze_text(text)

    if args.show_info:
        for msg in info:
            print(f"[INFO] {msg}")

    lexeme_tables_text = format_lexeme_tables(tables)
    token_table_text = format_token_table(tokens)
    sequence_text = format_sequence(tokens)
    sequence_json_text = format_sequence_json(tokens)

    print(token_table_text)
    print()
    print(sequence_text)

    if args.out_tables:
        Path(args.out_tables).write_text(lexeme_tables_text, encoding="utf-8")
    if args.out_tokens:
        Path(args.out_tokens).write_text(token_table_text + "\n", encoding="utf-8")
    if args.out_sequence:
        Path(args.out_sequence).write_text(sequence_json_text + "\n", encoding="utf-8")

    if errors:
        print()
        print("Лексический анализ завершён с ошибками.")
        for idx, err in enumerate(errors, start=1):
            print(f"{idx}. {err}")
        print(f"Обнаружено {len(tokens)} токенов. Количество ошибок: {len(errors)}.")
        return 1

    print()
    print(
        f"Лексический анализ завершён успешно. Обнаружено {len(tokens)} токенов. Ошибок не найдено."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
