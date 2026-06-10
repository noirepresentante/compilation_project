# ЛР3 — синтаксический анализатор

Модуль реализует синтаксический анализатор рекурсивного спуска для подмножества C++, использованного в `test/test.cpp`.
На вход подаётся поток токенов, полученный лексером ЛР2; для удобства parser.py может сам вызвать ЛР1 и ЛР2.

## Запуск ЛР3 на уже очищенном коде

```bash
python parser/parser.py test/test.cleaned.cpp
```

## Запуск ЛР3 сразу на исходном файле с использованием ЛР1 и ЛР2

```bash
python parser/parser.py test/test.cpp --raw --save-cleaned test/test.cleaned.cpp
```

## Сохранение AST и материалов отчёта

```bash
python parser/parser.py test/test.cleaned.cpp \
  --out-ast test/ast.json \
  --out-tree test/ast_tree.txt \
  --out-rules report/rule_trees.txt \
  --out-ast-structure report/ast_structure.txt
```

## Запуск от JSON-потока токенов, сохранённого ЛР2

```bash
python lexer/lexer.py test/test.cleaned.cpp --out-sequence test/token_sequence.json
python parser/parser.py --tokens-json test/token_sequence.json --out-ast test/ast.json
```

При синтаксической ошибке программа выводит тип ошибки, позицию в исходном коде, ожидаемую конструкцию и фактически найденный токен.
