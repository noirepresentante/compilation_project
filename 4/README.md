# Лабораторная работа 4

Папка содержит полный проект компилятора по ЛР1-ЛР4: препроцессор, лексический анализатор, синтаксический анализатор и семантический анализатор с генерацией триад.

## Полный запуск ЛР4 на исходном test.cpp

```bash
python semantic/semantic.py test/test.cpp --raw \
  --save-cleaned test/test.cleaned.cpp \
  --out-ast test/ast.json \
  --out-tree test/ast_tree.txt \
  --out-symbols test/symbol_table.txt \
  --out-triads test/triads.txt
```


## Вывод всех этапов при запуске ЛР4

По умолчанию `semantic.py` выводит только результат ЛР4: таблицу символов, триады и итог семантического анализа.
Если нужно показать результаты всех лабораторных работ в одном запуске, добавьте флаг `--output-all`:

```bash
python semantic/semantic.py test/test.cpp --raw --output-all
```

В этом режиме дополнительно выводятся: очищенный код ЛР1, таблицы лексем ЛР2, таблица токенов, последовательность токенов и AST ЛР3.

## Запуск отдельных этапов

```bash
python preprocessor/preprocess.py test/test.cpp -o test/test.cleaned.cpp
python lexer/lexer.py test/test.cleaned.cpp --out-sequence test/token_sequence.json
python parser/parser.py test/test.cpp --raw --out-ast test/ast.json --out-tree test/ast_tree.txt
python semantic/semantic.py test/test.cpp --raw --out-symbols test/symbol_table.txt --out-triads test/triads.txt
```

## Проверка семантических ошибок

```bash
python semantic/semantic.py test/test_error_semantic_undeclared.cpp --raw
python semantic/semantic.py test/test_error_semantic_redeclaration.cpp --raw
python semantic/semantic.py test/test_error_semantic_type_mismatch.cpp --raw
```

Основной отчёт и таблицы строятся по `test.cpp`. Файлы `test_error_*` предназначены только для проверки диагностики ошибок.

## Формат триад управляющих конструкций

В обновлённой версии триады для `if`, `for`, `while` и `range-for` используют реальные ссылки на номера триад. Например, `if_false, ^15, ^23` означает переход к триаде 23, если результат триады 15 ложный; `goto, ^14` означает безусловный переход к триаде 14.
