from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Подключаем модули ЛР1 и ЛР2 из текущей директории ЛР3.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexer.lexer import Token, analyze_text  # noqa: E402
from preprocessor.preprocess import preprocess_cpp  # noqa: E402


TYPE_KEYWORDS = {"int", "double", "bool", "char", "long"}
DECLARATION_START_KEYWORDS = {"int", "double", "bool", "char", "long", "const"}
ASSIGNMENT_OPERATORS = {"=", "+=", "*=", "-=", "/=", "%="}
BINARY_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    "<": 4,
    "<=": 4,
    ">": 4,
    "<<": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "%": 7,
}


@dataclass
class ASTNode:
    kind: str
    fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, ASTNode):
                return value.to_dict()
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return {"kind": self.kind, **{name: convert(value) for name, value in self.fields.items()}}


@dataclass
class ParserError(Exception):
    message: str
    line: int
    column: int
    expected: str
    found: str

    def __str__(self) -> str:
        location = f"строка {self.line}, столбец {self.column}" if self.line else "позиция неизвестна"
        return (
            f"Синтаксическая ошибка: {self.message}. "
            f"Место: {location}. Ожидалось: {self.expected}. Найдено: {self.found}."
        )


class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # ---------- Базовые операции над потоком токенов ----------

    def current(self) -> Optional[Token]:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Optional[Token]:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return None
        return self.tokens[idx]

    def at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    def token_repr(self, token: Optional[Token]) -> str:
        if token is None:
            return "конец потока токенов"
        return f"({token.type}, {token.value!r})"

    def error(self, message: str, expected: str) -> ParserError:
        token = self.current()
        if token is None:
            return ParserError(message, 0, 0, expected, "конец потока токенов")
        return ParserError(message, token.line, token.column, expected, self.token_repr(token))

    def match(self, token_type: Optional[str] = None, value: Optional[str] = None) -> Optional[Token]:
        token = self.current()
        if token is None:
            return None
        if token_type is not None and token.type != token_type:
            return None
        if value is not None and token.value != value:
            return None
        self.pos += 1
        return token

    def check(self, token_type: Optional[str] = None, value: Optional[str] = None) -> bool:
        token = self.current()
        if token is None:
            return False
        if token_type is not None and token.type != token_type:
            return False
        if value is not None and token.value != value:
            return False
        return True

    def expect(self, token_type: str, value: Optional[str] = None, expected: Optional[str] = None) -> Token:
        token = self.match(token_type, value)
        if token is None:
            expected_text = expected or (f"{token_type} {value!r}" if value is not None else token_type)
            raise self.error("нарушена ожидаемая структура программы", expected_text)
        return token

    def check_value(self, value: str) -> bool:
        token = self.current()
        return token is not None and token.value == value

    def expect_value(self, value: str, expected: Optional[str] = None) -> Token:
        token = self.current()
        if token is None or token.value != value:
            raise self.error("отсутствует обязательная лексема", expected or value)
        self.pos += 1
        return token

    # ---------- Верхний уровень ----------

    def parse(self) -> ASTNode:
        functions: List[ASTNode] = []
        while not self.at_end():
            functions.append(self.parse_function_definition())
        return ASTNode("Program", {"functions": functions})

    def parse_function_definition(self) -> ASTNode:
        return_type = self.parse_type()
        name_token = self.expect("IDENTIFIER", expected="имя функции")
        name = name_token.value
        self.expect_value("(", "открывающая скобка параметров '(' после имени функции")
        params = self.parse_parameter_list()
        self.expect_value(")", "закрывающая скобка параметров ')' после списка параметров")
        body = self.parse_block()
        return ASTNode(
            "FunctionDecl",
            {
                "return_type": return_type,
                "name": name,
                "params": params,
                "body": body,
                "line": name_token.line,
                "column": name_token.column,
            },
        )

    def parse_parameter_list(self) -> List[ASTNode]:
        params: List[ASTNode] = []
        if self.check_value(")"):
            return params
        while True:
            param_type = self.parse_type()
            name_token = self.expect("IDENTIFIER", expected="имя параметра")
            name = name_token.value
            params.append(ASTNode("Param", {"type": param_type, "name": name, "line": name_token.line, "column": name_token.column}))
            if not self.match("DELIMITER", ","):
                break
        return params

    def parse_type(self) -> ASTNode:
        is_const = bool(self.match("KEYWORD", "const"))
        name = ""
        generic_args: List[ASTNode] = []

        if self.match("KEYWORD", "long"):
            if self.match("KEYWORD", "long"):
                name = "long long"
            else:
                name = "long"
        elif self.check("KEYWORD") and self.current().value in {"int", "double", "bool", "char"}:
            name = self.current().value
            self.pos += 1
        elif self.check("IDENTIFIER", "std") and self.peek() is not None and self.peek().value == "::":
            self.expect("IDENTIFIER", "std")
            self.expect("OPERATOR", "::", "оператор разрешения области видимости '::'")
            type_name = self.expect("IDENTIFIER", expected="имя типа из пространства имён std").value
            name = f"std::{type_name}"
            if self.match("OPERATOR", "<"):
                generic_args.append(self.parse_type())
                self.expect("OPERATOR", ">", "закрывающая угловая скобка шаблона '>'")
        else:
            raise self.error("ожидался тип данных", "тип: int, double, bool, char, long long, const std::vector<T>& или std::string")

        is_reference = bool(self.match("OPERATOR", "&"))
        rendered = name
        if generic_args:
            rendered += "<" + ", ".join(arg.fields["name"] for arg in generic_args) + ">"
        if is_const:
            rendered = "const " + rendered
        if is_reference:
            rendered += "&"
        return ASTNode(
            "Type",
            {
                "name": rendered,
                "base": name,
                "const": is_const,
                "reference": is_reference,
                "generic_args": generic_args,
            },
        )

    # ---------- Операторы ----------

    def parse_block(self) -> ASTNode:
        self.expect_value("{", "открывающая фигурная скобка блока '{'")
        statements: List[ASTNode] = []
        while not self.check_value("}"):
            if self.at_end():
                raise self.error("незакрытый блок", "закрывающая фигурная скобка '}'")
            statements.append(self.parse_statement())
        self.expect_value("}", "закрывающая фигурная скобка блока '}'")
        return ASTNode("BlockStmt", {"statements": statements})

    def parse_statement(self) -> ASTNode:
        token = self.current()
        if token is None:
            raise self.error("ожидался оператор", "оператор или '}'")

        if token.value == "{":
            return self.parse_block()
        if token.type == "KEYWORD" and token.value == "if":
            return self.parse_if_stmt()
        if token.type == "KEYWORD" and token.value == "for":
            return self.parse_for_stmt()
        if token.type == "KEYWORD" and token.value == "while":
            return self.parse_while_stmt()
        if token.type == "KEYWORD" and token.value == "return":
            return self.parse_return_stmt()
        if self.is_declaration_start():
            return self.parse_var_decl_stmt(require_semicolon=True)

        expr = self.parse_expression()
        self.expect_value(";", "точка с запятой ';' после оператора-выражения")
        return ASTNode("ExprStmt", {"expr": expr})

    def parse_if_stmt(self) -> ASTNode:
        self.expect("KEYWORD", "if")
        self.expect_value("(", "открывающая скобка условия if")
        condition = self.parse_expression()
        self.expect_value(")", "закрывающая скобка условия if")
        then_branch = self.parse_statement()
        else_branch = None
        if self.match("KEYWORD", "else"):
            else_branch = self.parse_statement()
        return ASTNode("IfStmt", {"condition": condition, "then": then_branch, "else": else_branch})

    def parse_for_stmt(self) -> ASTNode:
        self.expect("KEYWORD", "for")
        self.expect_value("(", "открывающая скобка заголовка for")

        if self.is_declaration_start():
            init_type = self.parse_type()
            init_name_token = self.expect("IDENTIFIER", expected="имя переменной цикла")
            init_name = init_name_token.value
            if self.match("DELIMITER", ":"):
                iterable = self.parse_expression()
                self.expect_value(")", "закрывающая скобка range-for")
                body = self.parse_statement()
                return ASTNode(
                    "RangeForStmt",
                    {
                        "var": ASTNode("VarDecl", {"type": init_type, "name": init_name, "init": None, "line": init_name_token.line, "column": init_name_token.column}),
                        "iterable": iterable,
                        "body": body,
                    },
                )

            init_expr = None
            if self.match("OPERATOR", "="):
                init_expr = self.parse_expression()
            init = ASTNode("VarDecl", {"type": init_type, "name": init_name, "init": init_expr, "line": init_name_token.line, "column": init_name_token.column})
        elif not self.check_value(";"):
            init = self.parse_expression()
        else:
            init = None

        self.expect_value(";", "точка с запятой после инициализации for")
        condition = None if self.check_value(";") else self.parse_expression()
        self.expect_value(";", "точка с запятой после условия for")
        update = None if self.check_value(")") else self.parse_expression()
        self.expect_value(")", "закрывающая скобка заголовка for")
        body = self.parse_statement()
        return ASTNode("ForStmt", {"init": init, "condition": condition, "update": update, "body": body})

    def parse_while_stmt(self) -> ASTNode:
        self.expect("KEYWORD", "while")
        self.expect_value("(", "открывающая скобка условия while")
        condition = self.parse_expression()
        self.expect_value(")", "закрывающая скобка условия while")
        body = self.parse_statement()
        return ASTNode("WhileStmt", {"condition": condition, "body": body})

    def parse_return_stmt(self) -> ASTNode:
        self.expect("KEYWORD", "return")
        expr = None if self.check_value(";") else self.parse_expression()
        self.expect_value(";", "точка с запятой после return")
        return ASTNode("ReturnStmt", {"expr": expr})

    def parse_var_decl_stmt(self, require_semicolon: bool) -> ASTNode:
        var_type = self.parse_type()
        name_token = self.expect("IDENTIFIER", expected="имя переменной")
        name = name_token.value
        init = None
        if self.match("OPERATOR", "="):
            init = self.parse_expression()
        node = ASTNode("VarDeclStmt", {"declarations": [ASTNode("VarDecl", {"type": var_type, "name": name, "init": init, "line": name_token.line, "column": name_token.column})]})
        if require_semicolon:
            self.expect_value(";", "точка с запятой ';' после объявления переменной")
        return node

    def is_declaration_start(self) -> bool:
        token = self.current()
        if token is None:
            return False
        if token.type == "KEYWORD" and token.value in DECLARATION_START_KEYWORDS:
            return True
        if token.type == "IDENTIFIER" and token.value == "std" and self.peek() is not None and self.peek().value == "::":
            # В тестовой программе std::... в начале оператора используется только как тип.
            third = self.peek(2)
            return third is not None and third.value in {"vector", "string"}
        return False

    # ---------- Выражения ----------

    def parse_expression(self) -> ASTNode:
        return self.parse_assignment()

    def parse_assignment(self) -> ASTNode:
        left = self.parse_binary_expression(1)
        token = self.current()
        if token is not None and token.type == "OPERATOR" and token.value in ASSIGNMENT_OPERATORS:
            op = token.value
            self.pos += 1
            right = self.parse_assignment()
            return ASTNode("AssignExpr", {"operator": op, "left": left, "right": right})
        return left

    def parse_binary_expression(self, min_precedence: int) -> ASTNode:
        left = self.parse_unary()
        while True:
            token = self.current()
            if token is None or token.type != "OPERATOR" or token.value not in BINARY_PRECEDENCE:
                break
            precedence = BINARY_PRECEDENCE[token.value]
            if precedence < min_precedence:
                break
            op = token.value
            self.pos += 1
            right = self.parse_binary_expression(precedence + 1)
            left = ASTNode("BinaryExpr", {"operator": op, "left": left, "right": right})
        return left

    def parse_unary(self) -> ASTNode:
        token = self.current()
        if token is not None and token.type == "OPERATOR" and token.value in {"!", "++", "+", "-"}:
            op = token.value
            self.pos += 1
            operand = self.parse_unary()
            return ASTNode("UnaryExpr", {"operator": op, "prefix": True, "operand": operand})
        return self.parse_postfix()

    def parse_postfix(self) -> ASTNode:
        expr = self.parse_primary()
        while True:
            if self.match("DELIMITER", "("):
                args = self.parse_argument_list()
                self.expect_value(")", "закрывающая скобка вызова функции")
                expr = ASTNode("CallExpr", {"callee": expr, "args": args})
                continue
            if self.match("OPERATOR", "."):
                member = self.expect("IDENTIFIER", expected="имя поля или метода после '.'").value
                expr = ASTNode("MemberExpr", {"object": expr, "member": member})
                continue
            if self.match("OPERATOR", "++"):
                expr = ASTNode("UnaryExpr", {"operator": "++", "prefix": False, "operand": expr})
                continue
            break
        return expr

    def parse_argument_list(self) -> List[ASTNode]:
        args: List[ASTNode] = []
        if self.check_value(")"):
            return args
        while True:
            args.append(self.parse_expression())
            if not self.match("DELIMITER", ","):
                break
        return args

    def parse_primary(self) -> ASTNode:
        token = self.current()
        if token is None:
            raise self.error("неожиданный конец выражения", "идентификатор, константа, вызов или '('")

        if token.type in {"CONSTANT_INT", "CONSTANT_FLOAT", "CONSTANT_STRING", "CONSTANT_BOOL"}:
            self.pos += 1
            return ASTNode("LiteralExpr", {"literal_type": token.type, "value": token.value})

        if token.type == "IDENTIFIER":
            name = token.value
            self.pos += 1
            if self.match("OPERATOR", "::"):
                part = self.expect("IDENTIFIER", expected="имя после '::'").value
                name = f"{name}::{part}"
            return ASTNode("IdentifierExpr", {"name": name})

        if token.type == "KEYWORD" and token.value == "static_cast":
            self.pos += 1
            self.expect("OPERATOR", "<", "открывающая угловая скобка static_cast '<'")
            target_type = self.parse_type()
            self.expect("OPERATOR", ">", "закрывающая угловая скобка static_cast '>'")
            self.expect_value("(", "открывающая скобка аргумента static_cast")
            expr = self.parse_expression()
            self.expect_value(")", "закрывающая скобка аргумента static_cast")
            return ASTNode("CastExpr", {"target_type": target_type, "expr": expr})

        if self.match("DELIMITER", "("):
            expr = self.parse_expression()
            self.expect_value(")", "закрывающая круглая скобка выражения")
            return ASTNode("ParenExpr", {"expr": expr})

        raise self.error("неожиданный токен в выражении", "идентификатор, константа, вызов функции, static_cast или '('")


# ---------- Форматирование AST и деревьев правил ----------


def _format_scalar(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def format_ast(node: ASTNode) -> str:
    lines: List[str] = []

    def render_value(value: Any, prefix: str, connector: str, label: Optional[str] = None) -> None:
        label_prefix = f"{label}: " if label else ""
        if isinstance(value, ASTNode):
            lines.append(f"{prefix}{connector}{label_prefix}{value.kind}")
            render_fields(value, prefix + ("    " if connector == "└── " else "│   "))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{connector}{label_prefix}[]")
                return
            lines.append(f"{prefix}{connector}{label or 'items'}")
            child_prefix = prefix + ("    " if connector == "└── " else "│   ")
            for idx, item in enumerate(value):
                child_connector = "└── " if idx == len(value) - 1 else "├── "
                render_value(item, child_prefix, child_connector)
        else:
            lines.append(f"{prefix}{connector}{label_prefix}{_format_scalar(value)}")

    def render_fields(value: ASTNode, prefix: str) -> None:
        items = list(value.fields.items())
        for idx, (field_name, field_value) in enumerate(items):
            connector = "└── " if idx == len(items) - 1 else "├── "
            render_value(field_value, prefix, connector, field_name)

    lines.append(node.kind)
    render_fields(node, "")
    return "\n".join(lines)


RULE_TREES = """
Деревья правил для конструкций, использованных в test.cpp

1. Program
Program
└── FunctionDecl*
    ├── Type
    ├── IDENTIFIER(name)
    ├── '('
    ├── ParamList?
    ├── ')'
    └── BlockStmt

2. Type
Type
├── KEYWORD int | double | bool | char
├── KEYWORD long → [KEYWORD long]
├── KEYWORD const → Type → ['&']
└── IDENTIFIER std → OPERATOR :: → IDENTIFIER vector|string
    ├── vector → '<' Type '>'
    └── ['&']

3. BlockStmt
BlockStmt
├── '{'
├── Statement*
└── '}'

4. Statement
Statement
├── VarDeclStmt
├── IfStmt
├── ForStmt
├── RangeForStmt
├── WhileStmt
├── ReturnStmt
├── BlockStmt
└── ExprStmt

5. VarDeclStmt
VarDeclStmt
├── Type
├── IDENTIFIER(name)
├── ['=' Expression]
└── ';'

6. IfStmt
IfStmt
├── KEYWORD if
├── '('
├── Expression(condition)
├── ')'
├── Statement(then)
└── [KEYWORD else → Statement(else)]

7. ForStmt / RangeForStmt
ForStmt
├── KEYWORD for
├── '('
├── init: VarDecl | Expression | empty
├── ';'
├── condition: Expression | empty
├── ';'
├── update: Expression | empty
├── ')'
└── Statement(body)

RangeForStmt
├── KEYWORD for
├── '('
├── Type
├── IDENTIFIER(name)
├── ':'
├── Expression(iterable)
├── ')'
└── Statement(body)

8. WhileStmt
WhileStmt
├── KEYWORD while
├── '('
├── Expression(condition)
├── ')'
└── Statement(body)

9. ReturnStmt
ReturnStmt
├── KEYWORD return
├── [Expression]
└── ';'

10. Expression
Expression
└── Assignment
    ├── BinaryExpr
    └── [assignment_operator Assignment]

BinaryExpr
├── UnaryExpr
└── (operator UnaryExpr)*
    ├── multiplicative: *, /, %
    ├── additive: +, -
    ├── shift/output: <<
    ├── relational: <, <=, >
    ├── equality: ==, !=
    ├── logical_and: &&
    └── logical_or: ||

UnaryExpr
├── OPERATOR ! | ++ | + | - → UnaryExpr
└── PostfixExpr

PostfixExpr
├── PrimaryExpr
├── ['(' ArgumentList? ')']*
├── ['.' IDENTIFIER]*
└── [OPERATOR ++]*

PrimaryExpr
├── IDENTIFIER [OPERATOR :: IDENTIFIER]
├── CONSTANT_INT | CONSTANT_FLOAT | CONSTANT_STRING | CONSTANT_BOOL
├── KEYWORD static_cast '<' Type '>' '(' Expression ')'
└── '(' Expression ')'
""".strip()


AST_STRUCTURE = """
Структура AST

Program
- functions: список FunctionDecl.

FunctionDecl
- return_type: Type;
- name: имя функции;
- params: список Param;
- body: BlockStmt.

Type
- name: итоговое имя типа, например int, bool, long long, const std::vector<int>&;
- base: базовый тип;
- const: признак const;
- reference: признак ссылки;
- generic_args: аргументы шаблонного типа.

Param
- type: Type;
- name: имя параметра.

BlockStmt
- statements: список операторов блока.

VarDeclStmt / VarDecl
- declarations: список объявлений;
- type: Type;
- name: имя переменной;
- init: начальное выражение или None.

IfStmt
- condition: условие;
- then: оператор или блок ветки if;
- else: оператор или блок ветки else, либо None.

ForStmt
- init: объявление/выражение инициализации или None;
- condition: условие или None;
- update: выражение обновления или None;
- body: тело цикла.

RangeForStmt
- var: объявление переменной цикла;
- iterable: выражение-источник;
- body: тело цикла.

WhileStmt
- condition: условие;
- body: тело цикла.

ReturnStmt
- expr: возвращаемое выражение или None.

ExprStmt
- expr: выражение.

AssignExpr
- operator: =, +=, *= и др.;
- left: левая часть;
- right: правая часть.

BinaryExpr
- operator: бинарный оператор;
- left/right: операнды.

UnaryExpr
- operator: унарный оператор;
- prefix: true для префиксной формы, false для постфиксной;
- operand: операнд.

CallExpr
- callee: вызываемое выражение;
- args: аргументы.

MemberExpr
- object: объект;
- member: поле или метод.

IdentifierExpr
- name: имя идентификатора, включая std::cout при наличии оператора ::.

LiteralExpr
- literal_type: тип токена константы;
- value: текстовое значение константы.

CastExpr
- target_type: целевой Type;
- expr: приводимое выражение.

ParenExpr
- expr: выражение внутри скобок.
""".strip()


def load_tokens_from_json(path: Path) -> List[Token]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tokens: List[Token] = []
    for item in payload:
        tokens.append(Token(item["type"], item["value"], int(item.get("line", 0)), int(item.get("column", 0))))
    return tokens


def analyze_source(path: Path, raw: bool, save_cleaned: Optional[Path]) -> Tuple[List[Token], List[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Не удалось прочитать входной файл как UTF-8") from exc

    messages: List[str] = []
    if raw:
        cleaned, prep_info, prep_errors = preprocess_cpp(text)
        messages.extend(f"[PREPROCESSOR] {msg}" for msg in prep_info)
        if prep_errors:
            joined = "\n".join(str(err) for err in prep_errors)
            raise RuntimeError("Препроцессор обнаружил ошибки:\n" + joined)
        text = cleaned
        if save_cleaned is not None:
            save_cleaned.write_text(cleaned, encoding="utf-8")
            messages.append(f"[INFO] Очищенный код сохранён в: {save_cleaned}")

    tokens, lex_errors, lex_info, _tables = analyze_text(text)
    messages.extend(f"[LEXER] {msg}" for msg in lex_info)
    if lex_errors:
        joined = "\n".join(str(err) for err in lex_errors)
        raise RuntimeError("Лексический анализатор обнаружил ошибки:\n" + joined)
    return tokens, messages


def run_parser(tokens: List[Token]) -> ASTNode:
    parser = Parser(tokens)
    return parser.parse()


def main() -> int:
    cli = argparse.ArgumentParser(
        description="Синтаксический анализатор рекурсивного спуска для подмножества C++ из test.cpp"
    )
    cli.add_argument("input", nargs="?", help="Путь к .cpp файлу. Не требуется, если указан --tokens-json")
    cli.add_argument("--raw", action="store_true", help="Сначала выполнить очистку исходника модулем ЛР1")
    cli.add_argument("--save-cleaned", help="Сохранить очищенный код при использовании --raw")
    cli.add_argument("--tokens-json", help="Прочитать поток токенов из JSON, сохранённого лексером ЛР2")
    cli.add_argument("--out-ast", help="Сохранить AST в JSON")
    cli.add_argument("--out-tree", help="Сохранить печатное дерево AST")
    cli.add_argument("--out-rules", help="Сохранить деревья правил")
    cli.add_argument("--out-ast-structure", help="Сохранить описание структуры AST")
    args = cli.parse_args()

    try:
        if args.tokens_json:
            tokens = load_tokens_from_json(Path(args.tokens_json))
            messages: List[str] = []
        else:
            if not args.input:
                print("[ERROR] Укажите входной .cpp файл или --tokens-json", file=sys.stderr)
                return 2
            save_cleaned = Path(args.save_cleaned) if args.save_cleaned else None
            tokens, messages = analyze_source(Path(args.input), args.raw, save_cleaned)

        for msg in messages:
            print(msg)

        ast = run_parser(tokens)
        tree_text = format_ast(ast)
        ast_json = json.dumps(ast.to_dict(), ensure_ascii=False, indent=2)

        print("Абстрактное синтаксическое дерево (AST):")
        print(tree_text)
        print()
        print("Синтаксический анализ завершён успешно. Ошибок не найдено.")

        if args.out_ast:
            Path(args.out_ast).write_text(ast_json + "\n", encoding="utf-8")
        if args.out_tree:
            Path(args.out_tree).write_text(tree_text + "\n", encoding="utf-8")
        if args.out_rules:
            Path(args.out_rules).write_text(RULE_TREES + "\n", encoding="utf-8")
        if args.out_ast_structure:
            Path(args.out_ast_structure).write_text(AST_STRUCTURE + "\n", encoding="utf-8")
        return 0
    except ParserError as err:
        print(str(err), file=sys.stderr)
        print("Синтаксический анализ завершён с ошибками.", file=sys.stderr)
        return 1
    except RuntimeError as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
