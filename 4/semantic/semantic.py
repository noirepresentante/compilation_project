from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexer.lexer import (  # noqa: E402
    analyze_text,
    format_lexeme_tables,
    format_sequence,
    format_token_table,
)
from parser.parser import ASTNode, ParserError, analyze_source, format_ast, load_tokens_from_json, run_parser  # noqa: E402
from preprocessor.preprocess import preprocess_cpp  # noqa: E402


NUMERIC_TYPES = {"int", "long", "long long", "double"}
BOOL_TYPE = "bool"
STRING_TYPES = {"std::string"}
CHAR_TYPE = "char"
STREAM_TYPE = "std::ostream"
UNKNOWN_TYPE = "unknown"
VOID_TYPE = "void"


@dataclass
class Symbol:
    name: str
    type: str
    category: str
    scope: str
    declared: bool
    initialized: bool
    line: int = 0
    column: int = 0
    extra: str = ""


@dataclass
class SemanticError:
    message: str
    line: int = 0
    column: int = 0

    def __str__(self) -> str:
        loc = f"строка {self.line}, столбец {self.column}: " if self.line else ""
        return f"Семантическая ошибка: {loc}{self.message}"


@dataclass
class Triad:
    index: int
    operation: str
    operand1: str
    operand2: str = ""

    def render(self) -> str:
        return f"{self.index}) ({self.operation}, {self.operand1}, {self.operand2})" if self.operand2 != "" else f"{self.index}) ({self.operation}, {self.operand1})"


class Scope:
    def __init__(self, name: str, parent: Optional["Scope"] = None) -> None:
        self.name = name
        self.parent = parent
        self.symbols: Dict[str, Symbol] = {}

    def resolve(self, name: str) -> Optional[Symbol]:
        scope: Optional[Scope] = self
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None


class SemanticAnalyzer:
    def __init__(self) -> None:
        self.global_scope = Scope("global")
        self.scope = self.global_scope
        self.errors: List[SemanticError] = []
        self.symbols: List[Symbol] = []
        self.triads: List[Triad] = []
        self.functions: Dict[str, Symbol] = {}
        self.current_function: Optional[Symbol] = None
        self.scope_counter = 0
        self._install_builtins()

    def _install_builtins(self) -> None:
        for sym in [
            Symbol("std::cout", STREAM_TYPE, "builtin", "global", True, True, extra="стандартный поток вывода"),
        ]:
            self.global_scope.symbols[sym.name] = sym
            self.symbols.append(sym)

    def add_error(self, message: str, node: Optional[ASTNode] = None) -> None:
        line = int(node.fields.get("line", 0)) if isinstance(node, ASTNode) else 0
        column = int(node.fields.get("column", 0)) if isinstance(node, ASTNode) else 0
        self.errors.append(SemanticError(message, line, column))

    def type_name(self, type_node: ASTNode) -> str:
        return str(type_node.fields.get("name", UNKNOWN_TYPE))

    def normalize_type(self, type_name: str) -> str:
        return type_name.replace("const ", "").replace("&", "").strip()

    def declare(self, name: str, type_name: str, category: str, node: Optional[ASTNode], initialized: bool, extra: str = "") -> Symbol:
        line = int(node.fields.get("line", 0)) if isinstance(node, ASTNode) else 0
        column = int(node.fields.get("column", 0)) if isinstance(node, ASTNode) else 0
        if name in self.scope.symbols:
            self.add_error(f"повторное объявление идентификатора '{name}' в области видимости '{self.scope.name}'", node)
            existing = self.scope.symbols[name]
            return existing
        sym = Symbol(name, type_name, category, self.scope.name, True, initialized, line, column, extra)
        self.scope.symbols[name] = sym
        self.symbols.append(sym)
        return sym

    def push_scope(self, prefix: str) -> None:
        self.scope_counter += 1
        self.scope = Scope(f"{prefix}_{self.scope_counter}", self.scope)

    def pop_scope(self) -> None:
        if self.scope.parent is not None:
            self.scope = self.scope.parent

    def next_triad_index(self) -> int:
        return len(self.triads) + 1

    def triad_ref(self, index: int) -> str:
        return f"^{index}"

    def new_triad(self, operation: str, operand1: str, operand2: str = "") -> str:
        triad = Triad(self.next_triad_index(), operation, operand1, operand2)
        self.triads.append(triad)
        return self.triad_ref(triad.index)

    def patch_triad(self, index: int, operand1: Optional[str] = None, operand2: Optional[str] = None) -> None:
        triad = self.triads[index - 1]
        if operand1 is not None:
            triad.operand1 = operand1
        if operand2 is not None:
            triad.operand2 = operand2

    def analyze(self, ast: ASTNode) -> Tuple[List[Symbol], List[SemanticError], List[Triad]]:
        if ast.kind != "Program":
            self.add_error("корнем AST должен быть Program")
            return self.symbols, self.errors, self.triads

        for fn in ast.fields.get("functions", []):
            self.declare_function_header(fn)
        for fn in ast.fields.get("functions", []):
            self.analyze_function(fn)
        return self.symbols, self.errors, self.triads

    def declare_function_header(self, fn: ASTNode) -> None:
        name = fn.fields["name"]
        return_type = self.type_name(fn.fields["return_type"])
        params = fn.fields.get("params", [])
        signature = ", ".join(self.type_name(p.fields["type"]) for p in params)
        sym = self.declare(name, return_type, "function", fn, True, extra=f"({signature})")
        self.functions[name] = sym

    def analyze_function(self, fn: ASTNode) -> None:
        fn_sym = self.functions.get(fn.fields["name"])
        self.current_function = fn_sym
        self.push_scope(f"function_{fn.fields['name']}")
        for param in fn.fields.get("params", []):
            self.declare(param.fields["name"], self.type_name(param.fields["type"]), "parameter", param, True)
        self.analyze_block(fn.fields["body"], create_scope=False)
        self.pop_scope()
        self.current_function = None

    def analyze_block(self, block: ASTNode, create_scope: bool = True) -> None:
        if create_scope:
            self.push_scope("block")
        for stmt in block.fields.get("statements", []):
            self.analyze_statement(stmt)
        if create_scope:
            self.pop_scope()

    def analyze_statement(self, stmt: ASTNode) -> None:
        kind = stmt.kind
        if kind == "BlockStmt":
            self.analyze_block(stmt)
        elif kind == "VarDeclStmt":
            for decl in stmt.fields.get("declarations", []):
                self.analyze_var_decl(decl)
        elif kind == "IfStmt":
            cond_type, cond_place = self.analyze_expr(stmt.fields["condition"])
            if not self.is_condition_type(cond_type):
                self.add_error(f"условие if должно иметь тип bool или числовой тип, получен '{cond_type}'", stmt)

            if_false_index = self.next_triad_index()
            self.new_triad("if_false", cond_place, "?")
            self.analyze_statement(stmt.fields["then"])

            else_stmt = stmt.fields.get("else")
            if else_stmt is not None:
                goto_end_index = self.next_triad_index()
                self.new_triad("goto", "?", "")
                else_start = self.next_triad_index()
                self.patch_triad(if_false_index, operand2=self.triad_ref(else_start))
                self.analyze_statement(else_stmt)
                end_index = self.next_triad_index()
                self.patch_triad(goto_end_index, operand1=self.triad_ref(end_index))
            else:
                end_index = self.next_triad_index()
                self.patch_triad(if_false_index, operand2=self.triad_ref(end_index))
        elif kind == "ForStmt":
            self.push_scope("for")
            init = stmt.fields.get("init")
            if isinstance(init, ASTNode):
                if init.kind == "VarDecl":
                    self.analyze_var_decl(init)
                else:
                    self.analyze_expr(init)

            loop_start = self.next_triad_index()
            if_false_index: Optional[int] = None
            cond = stmt.fields.get("condition")
            if cond is not None:
                cond_type, cond_place = self.analyze_expr(cond)
                if not self.is_condition_type(cond_type):
                    self.add_error(f"условие for должно иметь тип bool или числовой тип, получен '{cond_type}'", stmt)
                if_false_index = self.next_triad_index()
                self.new_triad("if_false", cond_place, "?")

            update = stmt.fields.get("update")
            self.analyze_statement(stmt.fields["body"])
            if update is not None:
                self.analyze_expr(update)
            self.new_triad("goto", self.triad_ref(loop_start), "")
            if if_false_index is not None:
                self.patch_triad(if_false_index, operand2=self.triad_ref(self.next_triad_index()))
            self.pop_scope()
        elif kind == "RangeForStmt":
            self.push_scope("range_for")
            iterable_type, iterable_place = self.analyze_expr(stmt.fields["iterable"])
            if not self.normalize_type(iterable_type).startswith("std::vector"):
                self.add_error(f"range-for ожидает std::vector<T>, получен '{iterable_type}'", stmt)
            var = stmt.fields["var"]
            self.declare(var.fields["name"], self.type_name(var.fields["type"]), "range variable", var, True)

            loop_start = self.next_triad_index()
            if_false_index = self.next_triad_index()
            self.new_triad("range_has_next", iterable_place, "?")
            self.new_triad("range_next", var.fields["name"], iterable_place)
            self.analyze_statement(stmt.fields["body"])
            self.new_triad("goto", self.triad_ref(loop_start), "")
            self.patch_triad(if_false_index, operand2=self.triad_ref(self.next_triad_index()))
            self.pop_scope()
        elif kind == "WhileStmt":
            loop_start = self.next_triad_index()
            cond_type, cond_place = self.analyze_expr(stmt.fields["condition"])
            if not self.is_condition_type(cond_type):
                self.add_error(f"условие while должно иметь тип bool или числовой тип, получен '{cond_type}'", stmt)
            if_false_index = self.next_triad_index()
            self.new_triad("if_false", cond_place, "?")
            self.analyze_statement(stmt.fields["body"])
            self.new_triad("goto", self.triad_ref(loop_start), "")
            self.patch_triad(if_false_index, operand2=self.triad_ref(self.next_triad_index()))
        elif kind == "ReturnStmt":
            expr = stmt.fields.get("expr")
            if expr is None:
                ret_type, ret_place = VOID_TYPE, ""
            else:
                ret_type, ret_place = self.analyze_expr(expr)
            expected = self.current_function.type if self.current_function is not None else UNKNOWN_TYPE
            if not self.is_assignable(expected, ret_type):
                self.add_error(f"тип возвращаемого выражения '{ret_type}' несовместим с типом функции '{expected}'", stmt)
            self.new_triad("return", ret_place, "")
        elif kind == "ExprStmt":
            self.analyze_expr(stmt.fields["expr"])
        else:
            self.add_error(f"неподдерживаемый оператор AST '{kind}'", stmt)

    def analyze_var_decl(self, decl: ASTNode) -> None:
        name = decl.fields["name"]
        type_name = self.type_name(decl.fields["type"])
        init = decl.fields.get("init")
        default_initialized = init is not None or self.normalize_type(type_name).startswith("std::")
        sym = self.declare(name, type_name, "variable", decl, default_initialized)
        if init is not None:
            init_type, init_place = self.analyze_expr(init)
            if not self.is_assignable(type_name, init_type):
                self.add_error(f"тип инициализатора '{init_type}' несовместим с типом переменной '{type_name}'", decl)
            sym.initialized = True
            self.new_triad(":=", name, init_place)

    def analyze_expr(self, expr: ASTNode) -> Tuple[str, str]:
        kind = expr.kind
        if kind == "LiteralExpr":
            lit_type = expr.fields.get("literal_type")
            value = str(expr.fields.get("value"))
            if lit_type == "CONSTANT_INT":
                return "int", value
            if lit_type == "CONSTANT_FLOAT":
                return "double", value
            if lit_type == "CONSTANT_BOOL":
                return "bool", value
            if lit_type == "CONSTANT_STRING":
                if value.startswith("'"):
                    return "char", value
                return "std::string", value
            return UNKNOWN_TYPE, value
        if kind == "IdentifierExpr":
            name = str(expr.fields["name"])
            sym = self.scope.resolve(name) or self.global_scope.resolve(name)
            if sym is None:
                if name in self.functions:
                    return self.functions[name].type, name
                self.add_error(f"использование необъявленного идентификатора '{name}'", expr)
                return UNKNOWN_TYPE, name
            if sym.category in {"variable", "parameter", "range variable"} and not sym.initialized:
                self.add_error(f"использование неинициализированной переменной '{name}'", expr)
            return sym.type, name
        if kind == "ParenExpr":
            return self.analyze_expr(expr.fields["expr"])
        if kind == "CastExpr":
            source_type, source_place = self.analyze_expr(expr.fields["expr"])
            target = self.type_name(expr.fields["target_type"])
            result = self.new_triad("cast " + target, source_place, "")
            return target, result
        if kind == "MemberExpr":
            obj_type, obj_place = self.analyze_expr(expr.fields["object"])
            member = expr.fields["member"]
            return self.member_type(obj_type, member), f"{obj_place}.{member}"
        if kind == "CallExpr":
            return self.analyze_call(expr)
        if kind == "UnaryExpr":
            operand_type, operand_place = self.analyze_expr(expr.fields["operand"])
            op = expr.fields["operator"]
            if op == "!":
                if not self.is_condition_type(operand_type):
                    self.add_error(f"оператор ! неприменим к типу '{operand_type}'", expr)
                return "bool", self.new_triad(op, operand_place, "")
            if op == "++":
                if self.normalize_type(operand_type) not in NUMERIC_TYPES:
                    self.add_error(f"оператор ++ применим только к числовым типам, получен '{operand_type}'", expr)
                return operand_type, self.new_triad("++", operand_place, "")
            if op in {"+", "-"}:
                if self.normalize_type(operand_type) not in NUMERIC_TYPES:
                    self.add_error(f"унарный оператор {op} применим только к числовым типам, получен '{operand_type}'", expr)
                return operand_type, self.new_triad(op, operand_place, "")
        if kind == "BinaryExpr":
            left_type, left_place = self.analyze_expr(expr.fields["left"])
            right_type, right_place = self.analyze_expr(expr.fields["right"])
            op = expr.fields["operator"]
            result_type = self.binary_result_type(op, left_type, right_type, expr)
            return result_type, self.new_triad(op, left_place, right_place)
        if kind == "AssignExpr":
            left = expr.fields["left"]
            left_type, left_place = self.analyze_lvalue(left)
            right_type, right_place = self.analyze_expr(expr.fields["right"])
            op = expr.fields["operator"]
            if not self.is_assignable(left_type, right_type):
                self.add_error(f"тип правой части '{right_type}' несовместим с типом левой части '{left_type}'", expr)
            self.mark_initialized(left)
            return left_type, self.new_triad(op if op != "=" else ":=", left_place, right_place)
        self.add_error(f"неподдерживаемое выражение AST '{kind}'", expr)
        return UNKNOWN_TYPE, "?"

    def analyze_lvalue(self, expr: ASTNode) -> Tuple[str, str]:
        if expr.kind == "IdentifierExpr":
            name = str(expr.fields["name"])
            sym = self.scope.resolve(name) or self.global_scope.resolve(name)
            if sym is None:
                self.add_error(f"присваивание необъявленному идентификатору '{name}'", expr)
                return UNKNOWN_TYPE, name
            return sym.type, name
        if expr.kind == "MemberExpr":
            return self.analyze_expr(expr)
        self.add_error("левая часть присваивания должна быть идентификатором или обращением к члену объекта", expr)
        return self.analyze_expr(expr)

    def mark_initialized(self, expr: ASTNode) -> None:
        if expr.kind == "IdentifierExpr":
            sym = self.scope.resolve(str(expr.fields["name"])) or self.global_scope.resolve(str(expr.fields["name"]))
            if sym is not None:
                sym.initialized = True

    def analyze_call(self, expr: ASTNode) -> Tuple[str, str]:
        callee = expr.fields["callee"]
        args = expr.fields.get("args", [])
        arg_results = [self.analyze_expr(arg) for arg in args]
        arg_types = [t for t, _ in arg_results]
        arg_places = [p for _, p in arg_results]

        if callee.kind == "IdentifierExpr":
            name = str(callee.fields["name"])
            if name not in self.functions:
                self.add_error(f"вызов необъявленной функции '{name}'", callee)
                return UNKNOWN_TYPE, self.new_triad("call " + name, ", ".join(arg_places), "")
            fn = self.functions[name]
            expected = self.parse_signature(fn.extra)
            if len(expected) != len(arg_types):
                self.add_error(f"функция '{name}' ожидает {len(expected)} арг., получено {len(arg_types)}", callee)
            else:
                for idx, (want, got) in enumerate(zip(expected, arg_types), start=1):
                    if not self.is_assignable(want, got):
                        self.add_error(f"аргумент {idx} функции '{name}' имеет тип '{got}', ожидался '{want}'", callee)
            return fn.type, self.new_triad("call " + name, ", ".join(arg_places), "")

        if callee.kind == "MemberExpr":
            obj_type, obj_place = self.analyze_expr(callee.fields["object"])
            member = callee.fields["member"]
            ret = self.member_call_type(obj_type, member, arg_types, callee)
            return ret, self.new_triad("call " + f"{obj_place}.{member}", ", ".join(arg_places), "")

        callee_type, callee_place = self.analyze_expr(callee)
        return callee_type, self.new_triad("call " + callee_place, ", ".join(arg_places), "")

    def parse_signature(self, sig: str) -> List[str]:
        sig = sig.strip()
        if not (sig.startswith("(") and sig.endswith(")")):
            return []
        inside = sig[1:-1].strip()
        return [] if not inside else [part.strip() for part in inside.split(",")]

    def member_type(self, obj_type: str, member: str) -> str:
        norm = self.normalize_type(obj_type)
        if norm == STREAM_TYPE:
            return STREAM_TYPE
        if norm.startswith("std::vector"):
            if member == "empty":
                return "function:bool"
            if member == "size":
                return "function:int"
            if member == "push_back":
                return "function:void"
        return UNKNOWN_TYPE

    def member_call_type(self, obj_type: str, member: str, arg_types: List[str], node: ASTNode) -> str:
        norm = self.normalize_type(obj_type)
        if norm.startswith("std::vector"):
            element_type = "int" if "<int>" in norm else UNKNOWN_TYPE
            if member == "empty" and len(arg_types) == 0:
                return "bool"
            if member == "size" and len(arg_types) == 0:
                return "int"
            if member == "push_back":
                if len(arg_types) != 1 or not self.is_assignable(element_type, arg_types[0]):
                    self.add_error(f"метод push_back ожидает один аргумент типа '{element_type}'", node)
                return VOID_TYPE
        self.add_error(f"неизвестный метод '{member}' для типа '{obj_type}'", node)
        return UNKNOWN_TYPE

    def binary_result_type(self, op: str, left: str, right: str, node: ASTNode) -> str:
        lnorm = self.normalize_type(left)
        rnorm = self.normalize_type(right)
        if op == "<<":
            if lnorm == STREAM_TYPE:
                return STREAM_TYPE
            return STREAM_TYPE if lnorm == UNKNOWN_TYPE else left
        if op in {"+", "-", "*", "/", "%"}:
            if lnorm in NUMERIC_TYPES and rnorm in NUMERIC_TYPES:
                if op == "%" and (lnorm == "double" or rnorm == "double"):
                    self.add_error("оператор % применим только к целочисленным типам", node)
                return "double" if "double" in {lnorm, rnorm} else ("long long" if "long long" in {lnorm, rnorm} else "int")
            self.add_error(f"оператор {op} ожидает числовые операнды, получены '{left}' и '{right}'", node)
            return UNKNOWN_TYPE
        if op in {"<", "<=", ">", ">=", "==", "!="}:
            if self.are_comparable(left, right):
                return "bool"
            self.add_error(f"оператор {op} неприменим к типам '{left}' и '{right}'", node)
            return "bool"
        if op in {"&&", "||"}:
            if self.is_condition_type(left) and self.is_condition_type(right):
                return "bool"
            self.add_error(f"логический оператор {op} ожидает bool/числовые операнды, получены '{left}' и '{right}'", node)
            return "bool"
        return UNKNOWN_TYPE

    def is_condition_type(self, type_name: str) -> bool:
        norm = self.normalize_type(type_name)
        return norm in NUMERIC_TYPES or norm == "bool" or norm == UNKNOWN_TYPE

    def are_comparable(self, left: str, right: str) -> bool:
        lnorm = self.normalize_type(left)
        rnorm = self.normalize_type(right)
        return lnorm == UNKNOWN_TYPE or rnorm == UNKNOWN_TYPE or lnorm == rnorm or (lnorm in NUMERIC_TYPES and rnorm in NUMERIC_TYPES)

    def is_assignable(self, target: str, source: str) -> bool:
        t = self.normalize_type(target)
        s = self.normalize_type(source)
        if t == UNKNOWN_TYPE or s == UNKNOWN_TYPE:
            return True
        if t == s:
            return True
        if t == "double" and s in NUMERIC_TYPES:
            return True
        if t == "long long" and s in {"int", "long"}:
            return True
        if t == "bool" and s in {"bool"}:
            return True
        return False


def symbols_to_text(symbols: List[Symbol]) -> str:
    header = f"{'Имя':<18} | {'Тип':<24} | {'Категория':<13} | {'Область':<18} | {'Объявл.':<7} | {'Иниц.':<6} | Строка"
    rows = [header, "-" * len(header)]
    for s in symbols:
        rows.append(f"{s.name:<18} | {s.type:<24} | {s.category:<13} | {s.scope:<18} | {str(s.declared):<7} | {str(s.initialized):<6} | {s.line or '-'}")
    return "\n".join(rows)


def triads_to_text(triads: List[Triad]) -> str:
    return "\n".join(t.render() for t in triads)


def analyze_ast(ast: ASTNode) -> Tuple[List[Symbol], List[SemanticError], List[Triad]]:
    analyzer = SemanticAnalyzer()
    return analyzer.analyze(ast)


def print_section(title: str, body: str = "") -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    if body:
        print(body)


def analyze_source_full(path: Path, raw: bool, save_cleaned: Optional[Path]) -> Tuple[List[Any], List[str], Optional[str], str, str, str]:
    """Выполняет ЛР1 и ЛР2 так же, как analyze_source(), но возвращает материалы для полного вывода."""
    try:
        source_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Не удалось прочитать входной файл как UTF-8") from exc

    messages: List[str] = []
    cleaned_text: Optional[str] = None
    text_for_lexer = source_text

    if raw:
        cleaned, prep_info, prep_errors = preprocess_cpp(source_text)
        messages.extend(f"[PREPROCESSOR] {msg}" for msg in prep_info)
        if prep_errors:
            joined = "\n".join(str(err) for err in prep_errors)
            raise RuntimeError("Препроцессор обнаружил ошибки:\n" + joined)
        cleaned_text = cleaned
        text_for_lexer = cleaned
        if save_cleaned is not None:
            save_cleaned.write_text(cleaned, encoding="utf-8")
            messages.append(f"[INFO] Очищенный код сохранён в: {save_cleaned}")

    tokens, lex_errors, lex_info, tables = analyze_text(text_for_lexer)
    messages.extend(f"[LEXER] {msg}" for msg in lex_info)
    if lex_errors:
        joined = "\n".join(str(err) for err in lex_errors)
        raise RuntimeError("Лексический анализатор обнаружил ошибки:\n" + joined)

    return (
        tokens,
        messages,
        cleaned_text,
        format_lexeme_tables(tables),
        format_token_table(tokens),
        format_sequence(tokens),
    )


def main() -> int:
    cli = argparse.ArgumentParser(description="Семантический анализатор и генератор триад для подмножества C++ из test.cpp")
    cli.add_argument("input", nargs="?", help="Путь к .cpp файлу. Не требуется, если указан --tokens-json")
    cli.add_argument("--raw", action="store_true", help="Сначала выполнить очистку исходника модулем ЛР1")
    cli.add_argument("--save-cleaned", help="Сохранить очищенный код при использовании --raw")
    cli.add_argument("--tokens-json", help="Прочитать поток токенов из JSON, сохранённого лексером ЛР2")
    cli.add_argument("--out-symbols", help="Сохранить таблицу символов")
    cli.add_argument("--out-triads", help="Сохранить триады")
    cli.add_argument("--out-ast", help="Сохранить AST в JSON")
    cli.add_argument("--out-tree", help="Сохранить печатное дерево AST")
    cli.add_argument("--output-all", action="store_true", help="Вывести результаты всех этапов ЛР1–ЛР4: очищенный код, таблицы лексем, токены, AST, таблицу символов и триады")
    args = cli.parse_args()

    try:
        cleaned_text: Optional[str] = None
        lexeme_tables_text = ""
        token_table_text = ""
        sequence_text = ""

        if args.tokens_json:
            tokens = load_tokens_from_json(Path(args.tokens_json))
            messages: List[str] = []
            if args.output_all:
                token_table_text = format_token_table(tokens)
                sequence_text = format_sequence(tokens)
        else:
            if not args.input:
                print("[ERROR] Укажите входной .cpp файл или --tokens-json", file=sys.stderr)
                return 2
            save_cleaned = Path(args.save_cleaned) if args.save_cleaned else None
            if args.output_all:
                tokens, messages, cleaned_text, lexeme_tables_text, token_table_text, sequence_text = analyze_source_full(
                    Path(args.input), args.raw, save_cleaned
                )
            else:
                tokens, messages = analyze_source(Path(args.input), args.raw, save_cleaned)

        for msg in messages:
            print(msg)

        ast = run_parser(tokens)
        ast_tree_text = format_ast(ast)
        ast_json_text = json.dumps(ast.to_dict(), ensure_ascii=False, indent=2)
        symbols, errors, triads = analyze_ast(ast)

        if args.out_ast:
            Path(args.out_ast).write_text(ast_json_text + "\n", encoding="utf-8")
        if args.out_tree:
            Path(args.out_tree).write_text(ast_tree_text + "\n", encoding="utf-8")

        sym_text = symbols_to_text(symbols)
        triad_text = triads_to_text(triads)

        if args.output_all:
            if cleaned_text is not None:
                print_section("ЛР1. Очищенный код", cleaned_text.rstrip())
            elif args.raw:
                print_section("ЛР1. Очищенный код", "Очищенный код недоступен: вход был передан через --tokens-json.")

            if lexeme_tables_text:
                print_section("ЛР2. Таблицы лексем", lexeme_tables_text.rstrip())
            print_section("ЛР2. Таблица токенов", token_table_text)
            print_section("ЛР2. Последовательность токенов", sequence_text)
            print_section("ЛР3. Абстрактное синтаксическое дерево (AST)", ast_tree_text)
            print_section("ЛР4. Таблица символов", sym_text)
            print_section("ЛР4. Триады", triad_text)
        else:
            print("Таблица символов:")
            print(sym_text)
            print("\nТриады:")
            print(triad_text)
        if args.out_symbols:
            Path(args.out_symbols).write_text(sym_text + "\n", encoding="utf-8")
        if args.out_triads:
            Path(args.out_triads).write_text(triad_text + "\n", encoding="utf-8")

        if errors:
            print("\nСемантический анализ завершён с ошибками.")
            for idx, err in enumerate(errors, start=1):
                print(f"{idx}. {err}")
            return 1
        print("\nСемантический анализ завершён успешно. Ошибок не найдено.")
        return 0
    except ParserError as err:
        print(str(err), file=sys.stderr)
        return 1
    except RuntimeError as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
